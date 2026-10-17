import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { API_ENDPOINTS, API_BASE_URL } from '../config';
import DOMPurify from 'dompurify';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FileText, Download, Server, Users, Activity, Clock, Loader2, KeyRound, Plus, Circle, CheckCircle2, Info, Layers, Database, Code, Copy, Check, Sparkles, ZoomIn, ZoomOut, RotateCcw, Maximize2, AlertCircle } from 'lucide-react';
import bourntecLogo from '../assets/bourntec_logo.png';
import ReactFlow, { Background, Controls } from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import mermaid from 'mermaid';
import { generateArchitectureDesignPDF } from './architecturePdfGenerator';

// Initialize mermaid with configuration
// Initialize mermaid with optimal high-clarity configuration
mermaid.initialize({
    startOnLoad: false,
    theme: 'neutral',
    securityLevel: 'loose',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    suppressErrorRendering: true,
    flowchart: {
        htmlLabels: true,
        useMaxWidth: false,
        curve: 'basis',
        padding: 24,
        nodeSpacing: 50,
        rankSpacing: 55,
        defaultRenderer: 'dagre-wrapper'
    },
    er: {
        useMaxWidth: false,
        fontSize: 16
    },
    sequence: {
        useMaxWidth: false,
        showSequenceNumbers: true,
        actorFontSize: 16,
        messageFontSize: 15,
        noteFontSize: 14
    },
    themeVariables: {
        fontSize: '16px',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        primaryColor: '#eef2ff',
        primaryTextColor: '#0f172a',
        primaryBorderColor: '#4f46e5',
        lineColor: '#1e293b',
        secondaryColor: '#f8fafc',
        tertiaryColor: '#ffffff',
        mainBkg: '#ffffff',
        nodeBorder: '#4f46e5',
        clusterBkg: '#f8fafc',
        clusterBorder: '#94a3b8',
        defaultLinkColor: '#1e293b',
        titleColor: '#0f172a',
        edgeLabelBackground: '#ffffff',
        actorBorder: '#4f46e5',
        actorBkg: '#eef2ff',
        actorTextColor: '#0f172a',
        actorLineColor: '#475569',
        signalColor: '#1e293b',
        signalTextColor: '#0f172a',
        labelBoxBkgColor: '#ffffff',
        labelBoxBorderColor: '#94a3b8',
        labelTextColor: '#0f172a',
        loopTextColor: '#0f172a',
        noteBorderColor: '#cbd5e1',
        noteBkgColor: '#fef3c7',
        noteTextColor: '#78350f'
    }
});

if (typeof mermaid !== 'undefined' && mermaid.parseError) {
    mermaid.parseError = () => {};
}

// Global serialization queue to ensure mermaid.render calls execute sequentially.
// Mermaid relies on singleton DOM manipulation in document.body which causes race conditions
// and crashes with "Cannot read properties of null (reading 'firstChild')" if multiple diagrams render concurrently.
let mermaidRenderQueue = Promise.resolve();

// Dedicated offscreen container for Mermaid rendering to prevent layout thrashing, scroll jumping, and screen flickering
let offscreenMermaidVault = null;
const getOffscreenMermaidVault = () => {
    if (typeof document === 'undefined') return null;
    let vault = document.getElementById('mermaid-offscreen-render-vault');
    if (!vault) {
        vault = document.createElement('div');
        vault.id = 'mermaid-offscreen-render-vault';
        vault.setAttribute('aria-hidden', 'true');
        vault.style.cssText = 'position:fixed;top:-99999px;left:-99999px;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none;z-index:-9999;';
        document.body.appendChild(vault);
    }
    return vault;
};

const safeRenderMermaid = (id, code) => {
    return new Promise((resolve, reject) => {
        mermaidRenderQueue = mermaidRenderQueue
            .catch(() => {}) // keep queue alive even if a previous diagram failed
            .then(async () => {
                const container = getOffscreenMermaidVault();
                try {
                    const res = await mermaid.render(id, code, container || undefined);
                    try {
                        if (container) container.innerHTML = '';
                        const el = document.getElementById(id);
                        if (el && el.parentNode) el.parentNode.removeChild(el);
                        const dEl = document.getElementById('d' + id);
                        if (dEl && dEl.parentNode) dEl.parentNode.removeChild(dEl);
                    } catch (e) {}
                    resolve(res);
                } catch (err) {
                    try {
                        if (container) container.innerHTML = '';
                        const el = document.getElementById(id);
                        if (el && el.parentNode) el.parentNode.removeChild(el);
                        const dEl = document.getElementById('d' + id);
                        if (dEl && dEl.parentNode) dEl.parentNode.removeChild(dEl);
                    } catch (e) {}
                    reject(err);
                }
            });
    });
};

// Helper to ensure architecture design markdown header always reflects current date
const sanitizeDesignMarkdownDate = (markdown) => {
    if (!markdown || typeof markdown !== 'string') return markdown;
    const currentDate = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    return markdown.replace(/(\*\*Date:\*\*)\s*[^\n\r]+/i, `$1 ${currentDate}  `);
};

// Helper to sanitize and fix common LLM Mermaid syntax errors and word truncations
const sanitizeMermaidCode = (rawCode) => {
    if (!rawCode || typeof rawCode !== 'string') return '';
    let cleaned = rawCode.trim();

    // 1. Strip wrapping markdown code block ticks if present
    cleaned = cleaned.replace(/^```(?:mermaid|erDiagram|erdiagram|flowchart|graph|sequenceDiagram|sequence|classDiagram|stateDiagram|c4)?\s*/i, '');
    cleaned = cleaned.replace(/\s*```$/, '');
    cleaned = cleaned.trim();

    // 2. Auto-repair common LLM word truncations in node/arrow labels
    cleaned = cleaned.replace(/\bAdministratc\b/gi, 'Administrator');
    cleaned = cleaned.replace(/\bStakehold\b/gi, 'Stakeholders');
    cleaned = cleaned.replace(/\bInteracts via H\b/gi, 'Interacts via HTTPS');
    cleaned = cleaned.replace(/\bValidates ident\b/gi, 'Validates Identity');
    cleaned = cleaned.replace(/\bDispatches ale\b/gi, 'Dispatches Alerts');
    cleaned = cleaned.replace(/\bExchanges dat\b/gi, 'Exchanges Data');

    // 3. Fix duplicate diagram headers at the start (e.g. erDiagram\nerDiagram or graph TD\ngraph TD)
    cleaned = cleaned.replace(/^(erDiagram|graph\s+[A-Z]+|flowchart\s+[A-Z]+|sequenceDiagram|classDiagram|stateDiagram)[\s\n]+\1/i, '$1');

    // 4. Detect if this is an Sequence diagram missing header
    const isSeq = cleaned.startsWith('sequenceDiagram') ||
                  cleaned.toLowerCase().startsWith('sequencediagram') ||
                  cleaned.includes('->>') ||
                  cleaned.includes('-->>');
    if (isSeq && !cleaned.toLowerCase().startsWith('sequencediagram')) {
        cleaned = 'sequenceDiagram\n' + cleaned;
    }

    // 5. Detect if this is an ER diagram
    const isEr = cleaned.startsWith('erDiagram') ||
                 cleaned.toLowerCase().startsWith('erdiagram') ||
                 cleaned.toLowerCase().includes('erdiagram') ||
                 cleaned.includes('||--') ||
                 cleaned.includes('}o--') ||
                 cleaned.includes('|o--');

    if (isEr) {
        const erIdx = cleaned.toLowerCase().indexOf('erdiagram');
        if (erIdx > 0) {
            cleaned = cleaned.substring(erIdx);
        } else if (!cleaned.toLowerCase().startsWith('erdiagram')) {
            cleaned = 'erDiagram\n' + cleaned;
        }

        // Deduplicate erDiagram if prepended
        cleaned = cleaned.replace(/^erDiagram[\s\n]+erDiagram/i, 'erDiagram');

        // Fix ER Diagram attribute lines:
        // LLMs frequently output: "datatype PK column_name" instead of "datatype column_name PK"
        const lines = cleaned.split('\n');
        const fixedLines = lines.map(line => {
            const trimmed = line.trim();
            // Remove invalid 'end' keyword lines in erDiagrams
            if (trimmed.toLowerCase() === 'end') return null;

            // Attribute ordering check
            const attrMatch = line.match(/^(\s*)([A-Za-z0-9_\[\]\<\>\.\(\)]+)\s+((?:PK|FK|UK)(?:\s*,?\s*(?:PK|FK|UK))*)\s+([A-Za-z0-9_]+)(.*)$/);
            if (attrMatch) {
                const [, indent, dataType, keys, attrName, rest] = attrMatch;
                const cleanKeys = keys.replace(/\s+/g, '');
                return `${indent}${dataType} ${attrName} ${cleanKeys}${rest}`;
            }

            const attrMatch2 = line.match(/^(\s*)((?:PK|FK|UK)(?:\s*,?\s*(?:PK|FK|UK))*)\s+([A-Za-z0-9_]+)\s+([A-Za-z0-9_\[\]\<\>\.\(\)]+)(.*)$/);
            if (attrMatch2) {
                const [, indent, keys, attrName, dataType, rest] = attrMatch2;
                const cleanKeys = keys.replace(/\s+/g, '');
                return `${indent}${dataType} ${attrName} ${cleanKeys}${rest}`;
            }

            return line;
        });

        cleaned = fixedLines.filter(l => l !== null).join('\n');
    } else {
        // Flowchart / Graph shape repairs:
        // Ensure titles and labels with spaces/parentheses/special characters are safely quoted:
        // Fix unquoted subgraph titles: subgraph ID [Title with special chars] -> subgraph ID ["Title..."]
        cleaned = cleaned.replace(/subgraph\s+([A-Za-z0-9_]+)\s*\[([^"\]\n]+)\]/g, (m, id, text) => {
            return `subgraph ${id}["${text.replace(/"/g, "'")}"]`;
        });
        // 1. Stadium shape: id([ ... ]) -> id(["..."])
        cleaned = cleaned.replace(/(\b\w+)\(\[\s*([^"\]\n]*?)\s*\]\)/g, (match, id, text) => {
            return `${id}(["${text.replace(/"/g, "'")}"])`;
        });
        // 2. Cylinder shape: id[( ... )] -> id[("...")]
        cleaned = cleaned.replace(/(\b\w+)\[\(\s*([^"\]\n]*?)\s*\)\]/g, (match, id, text) => {
            return `${id}[("${text.replace(/"/g, "'")}")]`;
        });
        // 3. Hexagon shape: id{{ ... }} -> id{{"..."}}
        cleaned = cleaned.replace(/(\b\w+)\{\{\s*([^"\}\n]*?)\s*\}\}/g, (match, id, text) => {
            return `${id}{{"${text.replace(/"/g, "'")}}"`;
        });
        // 4. Circle shape: id(( ... )) -> id(("..."))
        cleaned = cleaned.replace(/(\b\w+)\(\(\s*([^"\)\n]*?)\s*\)\)/g, (match, id, text) => {
            return `${id}(("${text.replace(/"/g, "'")}"))`;
        });
        // 5. Subroutine shape: id[[ ... ]] -> id[["..."]]
        cleaned = cleaned.replace(/(\b\w+)\[\[\s*([^"\]\n]*?)\s*\]\]/g, (match, id, text) => {
            return `${id}[["${text.replace(/"/g, "'")}"]]`;
        });
        // 6. Box shape: id[ ... ] -> id["..."]
        cleaned = cleaned.replace(/(\b\w+)\[([^"\]\n]*[\(\)\{\}&\/\\#][^"\]\n]*)\]/g, (match, id, text) => {
            return `${id}["${text.replace(/"/g, "'")}"]`;
        });
    }

    return cleaned.trim();
};

// Improved Mermaid Diagram Component with serialized rendering, smooth animation, and expand functionality
const MermaidDiagram = ({ code, showDownload = true }) => {
    const containerRef = useRef(null);
    const [svg, setSvg] = useState('');
    const [error, setError] = useState(null);
    const [downloading, setDownloading] = useState(false);
    const [isExpanded, setIsExpanded] = useState(false);
    const [isRendering, setIsRendering] = useState(false);
    const [zoomLevel, setZoomLevel] = useState(1);

    useEffect(() => {
        let cancelled = false;
        const renderDiagram = async () => {
            setIsRendering(true);
            try {
                const sanitized = sanitizeMermaidCode(code);
                const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
                const { svg: renderedSvg } = await safeRenderMermaid(id, sanitized);
                if (!cancelled) {
                    // Remove fixed height and restrictive max-width on root <svg> tag if viewBox is present,
                    // allowing the diagram to scale crisply to readable size without text squashing.
                    let cleanSvg = renderedSvg;
                    if (cleanSvg && /viewBox=/i.test(cleanSvg)) {
                        cleanSvg = cleanSvg
                            .replace(/(<svg\b[^>]*?)\sheight="[^"]*"/i, '$1')
                            .replace(/(<svg\b[^>]*?\sstyle="[^"]*?)height\s*:\s*[^;"]+;?/i, '$1')
                            .replace(/(<svg\b[^>]*?\sstyle="[^"]*?)max-width\s*:\s*[^;"]+;?/i, '$1');
                    }
                    setSvg(cleanSvg);
                    setError(null);
                    setIsRendering(false);
                }
            } catch (err) {
                console.warn('Mermaid render error:', err);
                if (!cancelled) {
                    setError(err.message || 'Failed to render diagram');
                    setSvg('');
                    setIsRendering(false);
                }
            }
        };
        renderDiagram();
        return () => { cancelled = true; };
    }, [code]);

    const handleExpand = () => {
        setZoomLevel(1);
        setIsExpanded(true);
    };

    const handleCloseExpanded = () => {
        setIsExpanded(false);
        setZoomLevel(1);
    };

    const handleZoomIn = () => {
        setZoomLevel(z => Math.min(Number((z + 0.25).toFixed(2)), 3.0));
    };

    const handleZoomOut = () => {
        setZoomLevel(z => Math.max(Number((z - 0.25).toFixed(2)), 0.5));
    };

    const handleResetZoom = () => {
        setZoomLevel(1);
    };

    const handleDownloadPNG = async () => {
        if (!svg || !containerRef.current) return;

        setDownloading(true);
        try {
            const svgElement = containerRef.current.querySelector('svg');
            if (!svgElement) throw new Error('SVG element not found');

            // Clone and force high-resolution dimensions using viewBox
            const clonedSvg = svgElement.cloneNode(true);
            const vb = svgElement.getAttribute('viewBox');
            let targetW = 2400;
            let targetH = 1200;

            if (vb) {
                const parts = vb.trim().split(/[\s,]+/);
                if (parts.length === 4) {
                    const vbW = parseFloat(parts[2]);
                    const vbH = parseFloat(parts[3]);
                    if (vbW > 0 && vbH > 0) {
                        targetH = Math.round(targetW * (vbH / vbW));
                    }
                }
            } else {
                const bbox = svgElement.getBBox();
                const w = bbox.width || svgElement.width.baseVal.value || 800;
                const h = bbox.height || svgElement.height.baseVal.value || 600;
                targetH = Math.round(targetW * (h / w));
            }

            clonedSvg.setAttribute('width', String(targetW));
            clonedSvg.setAttribute('height', String(targetH));
            clonedSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');

            const svgString = new XMLSerializer().serializeToString(clonedSvg);
            const svgDataUrl = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgString)));

            const img = new Image();
            img.onload = () => {
                try {
                    const scale = 2; // 2× on top of the already-large 2400px SVG = 4800px effective
                    const canvas = document.createElement('canvas');
                    canvas.width = targetW * scale;
                    canvas.height = targetH * scale;

                    const ctx = canvas.getContext('2d');
                    ctx.scale(scale, scale);
                    ctx.fillStyle = 'white';
                    ctx.fillRect(0, 0, targetW, targetH);
                    ctx.imageSmoothingEnabled = true;
                    ctx.imageSmoothingQuality = 'high';
                    ctx.drawImage(img, 0, 0, targetW, targetH);

                    canvas.toBlob((blob) => {
                        if (!blob) throw new Error('Failed to create image blob');
                        const url = URL.createObjectURL(blob);
                        const link = document.createElement('a');
                        link.href = url;
                        link.download = `diagram-${Date.now()}.png`;
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                        URL.revokeObjectURL(url);
                        setDownloading(false);
                    }, 'image/png');
                } catch (err) {
                    console.error('Canvas error:', err);
                    setDownloading(false);
                    alert('Failed to export diagram. Please try again.');
                }
            };

            img.onerror = (err) => {
                console.error('Image load error:', err);
                setDownloading(false);
                alert('Failed to load diagram for export. Please try again.');
            };

            img.src = svgDataUrl;
        } catch (err) {
            console.error('Download error:', err);
            alert('Failed to download diagram. Please try again.');
            setDownloading(false);
        }
    };

    if (error) {
        return (
            <div className="my-4 rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
                <div className="flex items-center justify-between px-4 py-2.5 bg-gray-50 border-b border-gray-200">
                    <span className="text-xs font-semibold text-gray-600 flex items-center gap-1.5">
                        <FileText className="w-3.5 h-3.5 text-gray-500" />
                        Diagram Source Code
                    </span>
                    <span className="text-[11px] text-amber-600 font-medium px-2 py-0.5 bg-amber-50 rounded border border-amber-200">
                        Syntax Error Fallback View
                    </span>
                </div>
                <pre className="p-4 bg-gray-900 text-gray-100 text-xs font-mono overflow-x-auto max-h-96">
                    <code>{code}</code>
                </pre>
            </div>
        );
    }

    if (isRendering || !svg) {
        return (
            <div className="flex items-center justify-center py-8 my-4 bg-gray-50 rounded-lg border border-gray-200">
                <div className="flex items-center gap-3">
                    <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
                    <span className="text-sm font-medium text-gray-600">Rendering high-clarity diagram...</span>
                </div>
            </div>
        );
    }

    return (
        <>
            {/* Fullscreen Expanded View Modal with Dynamic Zoom */}
            {isExpanded && (
                <div
                    className="fixed inset-0 z-[500] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in"
                    onClick={handleCloseExpanded}
                >
                    <div
                        className="relative w-full max-w-6xl max-h-[92vh] bg-white rounded-2xl shadow-2xl overflow-hidden flex flex-col animate-scale-in"
                        onClick={(e) => e.stopPropagation()}
                    >
                        {/* Modal Header */}
                        <div className="flex items-center justify-between px-6 py-3.5 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white border-b border-indigo-900/40">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center">
                                    <Maximize2 className="w-4 h-4 text-indigo-300" />
                                </div>
                                <div>
                                    <span className="font-semibold text-sm tracking-wide">High-Definition Architecture Diagram</span>
                                    <p className="text-[11px] text-indigo-200/70">Interactive vector canvas with dynamic zoom & inspection</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                {/* Zoom Controls */}
                                <div className="flex items-center bg-white/10 rounded-lg p-0.5 border border-white/15 mr-2">
                                    <button
                                        onClick={handleZoomOut}
                                        disabled={zoomLevel <= 0.5}
                                        className="p-1.5 hover:bg-white/15 disabled:opacity-30 disabled:hover:bg-transparent rounded transition-colors text-white"
                                        title="Zoom Out (Ctrl -)"
                                    >
                                        <ZoomOut className="w-3.5 h-3.5" />
                                    </button>
                                    <span className="px-2 text-xs font-mono font-medium text-white min-w-[44px] text-center">
                                        {Math.round(zoomLevel * 100)}%
                                    </span>
                                    <button
                                        onClick={handleZoomIn}
                                        disabled={zoomLevel >= 3.0}
                                        className="p-1.5 hover:bg-white/15 disabled:opacity-30 disabled:hover:bg-transparent rounded transition-colors text-white"
                                        title="Zoom In (Ctrl +)"
                                    >
                                        <ZoomIn className="w-3.5 h-3.5" />
                                    </button>
                                    <button
                                        onClick={handleResetZoom}
                                        className="p-1.5 hover:bg-white/15 rounded transition-colors text-white border-l border-white/15 ml-0.5"
                                        title="Reset Zoom"
                                    >
                                        <RotateCcw className="w-3.5 h-3.5" />
                                    </button>
                                </div>

                                <button
                                    onClick={handleDownloadPNG}
                                    disabled={downloading}
                                    className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800/50 rounded-lg shadow-sm transition-all"
                                >
                                    <Download className="w-3.5 h-3.5" />
                                    {downloading ? 'Exporting...' : 'Export 4K PNG'}
                                </button>
                                <button
                                    onClick={handleCloseExpanded}
                                    className="p-1.5 hover:bg-white/20 rounded-lg transition-all text-white/80 hover:text-white"
                                    title="Close"
                                >
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                    </svg>
                                </button>
                            </div>
                        </div>

                        {/* Expanded Diagram Content */}
                        <div className="p-8 bg-slate-50/90 overflow-auto flex-1 flex justify-center items-start min-h-[450px]">
                            <div
                                className="mermaid-diagram-container transition-transform duration-150 origin-top flex justify-center [&>svg]:!h-auto [&>svg]:w-auto [&>svg]:max-w-none shadow-sm bg-white p-6 rounded-xl border border-slate-200"
                                style={{ transform: `scale(${zoomLevel})` }}
                                dangerouslySetInnerHTML={{ __html: svg }}
                            />
                        </div>
                    </div>
                </div>
            )}

            {/* Normal View */}
            <div className="my-5 p-5 bg-white rounded-xl border border-gray-200/90 shadow-sm overflow-x-auto">
                {/* Action Buttons */}
                <div className="flex justify-between items-center mb-3">
                    <span className="text-[11px] font-semibold tracking-wider uppercase text-slate-500 flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse"></span>
                        Architecture Topology Diagram
                    </span>
                    <div className="flex items-center gap-2">
                        {/* Expand & Zoom Button */}
                        <button
                            onClick={handleExpand}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-300 rounded-lg shadow-sm transition-all hover:shadow"
                            title="Expand to Fullscreen & Zoom"
                        >
                            <Maximize2 className="w-3.5 h-3.5 text-slate-600" />
                            <span>Expand & Zoom</span>
                        </button>

                        {/* Download Button */}
                        {showDownload && (
                            <button
                                onClick={handleDownloadPNG}
                                disabled={downloading}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 rounded-lg shadow-sm transition-all"
                                title="Download 4K PNG"
                            >
                                {downloading ? (
                                    <>
                                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                        <span>Exporting...</span>
                                    </>
                                ) : (
                                    <>
                                        <Download className="w-3.5 h-3.5" />
                                        <span>Download PNG</span>
                                    </>
                                )}
                            </button>
                        )}
                    </div>
                </div>

                {/* SVG Diagram with smooth fade-in animation */}
                <div
                    ref={containerRef}
                    className="mermaid-diagram-container flex justify-center [&>svg]:max-w-full [&>svg]:min-w-[480px] sm:[&>svg]:min-w-[620px] [&>svg]:!h-auto [&>svg]:w-auto transition-opacity duration-300 ease-out py-2"
                    style={{ opacity: svg ? 1 : 0 }}
                    dangerouslySetInnerHTML={{ __html: svg }}
                />
            </div>
        </>
    );
};

const parseStoredDocumentAnalysis = (doc) => {
    try {
        return doc?.analysis_result ? JSON.parse(doc.analysis_result) : null;
    } catch {
        return null;
    }
};

const isPendingGovernanceAnalysis = (analysis) =>
    Boolean(analysis && analysis.screening_status === 'pending_governance_analysis');

const hasCompletedStoredAnalysis = (analysis) => {
    if (!analysis || isPendingGovernanceAnalysis(analysis)) {
        return false;
    }
    return String(analysis.analysis || '').trim().length > 0;
};

// Format error messages to be user-friendly
const formatAnalysisError = (error) => {
    let errorMessage = error?.message || String(error);

    // Attempt to extract detail from JSON-formatted backend errors
    try {
        if (errorMessage.startsWith('{') || errorMessage.includes('"detail"')) {
            const parsed = JSON.parse(errorMessage);
            if (parsed && parsed.detail) {
                errorMessage = parsed.detail;
            }
        }
    } catch (e) {
        // Not a valid JSON string or parse error, fallback to raw message
    }

    // Strip any leading "Error:" or "Exception:" or similar prefixes
    errorMessage = errorMessage.replace(/^(Error|Exception|Fail|Failure|Failed):\s*/i, '');

    // Check for specific error patterns and provide custom messages
    if (errorMessage.includes('TOKEN_EXHAUSTED')) {
        return 'Your token quota has been exhausted. Please contact your organization administrator to allocate more tokens.';
    }

    if (errorMessage.includes('PAYG_HARD_LIMIT_REACHED')) {
        return "Your organization's PAYG spending limit has been reached. Please contact your administrator.";
    }

    if (errorMessage.includes('PAYG access suspended') || errorMessage.includes('overdue') || errorMessage.includes('grace period')) {
        return 'Payment required. Your organization has overdue invoices exceeding its grace period.';
    }

    if (errorMessage.includes('ORGANIZATION_BLOCKED')) {
        return 'Your organization has been blocked. Please contact the administrator or review your billing status.';
    }

    if (errorMessage.includes('USER_BLOCKED')) {
        return 'Your user account has been blocked. Please contact your organization administrator.';
    }

    if (errorMessage.includes('PAYMENT_REQUIRED') || errorMessage.includes('402')) {
        return 'Payment required or token quota exhausted. Please check your token balance.';
    }

    if (errorMessage.includes('Analysis job not found') || errorMessage.includes('job not found')) {
        return 'The analysis session has expired or was not found. Please try starting the analysis again.';
    }

    if (errorMessage.includes('500 INTERNAL SERVER ERROR') || errorMessage.includes('Server error')) {
        return 'The AI service is currently unavailable. This could be due to high load or maintenance. Please try again in a few moments.';
    }

    if (errorMessage.includes('brn-llama.bourntec.com') || errorMessage.includes('api/process')) {
        return 'Unable to connect to the AI analysis service. Please check your network connection and try again.';
    }

    if (errorMessage.includes('Network') || errorMessage.includes('fetch')) {
        return 'Network connection error. Please check your internet connection and try again.';
    }

    if (errorMessage.includes('timeout') || errorMessage.includes('timed out')) {
        return 'The analysis is taking longer than expected. Please try again or contact support if the issue persists.';
    }

    if (errorMessage.includes('401') || errorMessage.includes('Unauthorized')) {
        return 'Your session has expired. Please log in again to continue.';
    }

    if (errorMessage.includes('403') || errorMessage.includes('Forbidden')) {
        return 'You do not have permission to perform this analysis. Please contact your administrator.';
    }

    // Return the original error message if no specific pattern matches
    return errorMessage;
};

// Utility: layout architecture graph with dagre so nodes don't overlap
const layoutArchitectureGraph = (nodes, edges, direction = 'TB') => {
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: direction, nodesep: 80, ranksep: 120 });
    g.setDefaultEdgeLabel(() => ({}));

    const NODE_WIDTH = 200;
    const NODE_HEIGHT = 60;

    nodes.forEach((node) => {
        const id = String(node.id || node.label);
        g.setNode(id, { width: NODE_WIDTH, height: NODE_HEIGHT });
    });

    edges.forEach((edge) => {
        if (!edge.from || !edge.to) return;
        g.setEdge(String(edge.from), String(edge.to));
    });

    dagre.layout(g);

    return nodes.map((node) => {
        const id = String(node.id || node.label);
        const dagreNode = g.node(id);
        const position = dagreNode
            ? { x: dagreNode.x - NODE_WIDTH / 2, y: dagreNode.y - NODE_HEIGHT / 2 }
            : { x: 0, y: 0 };
        return {
            id,
            data: { label: node.label || id },
            position,
        };
    });
};

const hasCompletedDocumentAnalysis = (doc) => hasCompletedStoredAnalysis(parseStoredDocumentAnalysis(doc));

// Component to display processed content in tabs
const ProcessedContentTabs = ({ sections, markdown }) => {
    const [activeTabIndex, setActiveTabIndex] = useState(0);

    // Parse sections from markdown if not provided as structured data
    let parsedSections = sections || [];

    if (!parsedSections || parsedSections.length === 0) {
        // Try to parse sections from markdown using the separator pattern
        if (markdown) {
            const sectionRegex = /---\s*([a-zA-Z0-9\s&()_.:/\\-]+)\s*---\s*([\s\S]*?)(?=---\s*[a-zA-Z0-9\s&()_.:/\\-]+\s*---|$)/g;
            const tempSections = [];
            let match;

            while ((match = sectionRegex.exec(markdown)) !== null) {
                tempSections.push({
                    title: match[1].trim(),
                    content: match[2].trim()
                });
            }

            if (tempSections.length > 0) {
                parsedSections = tempSections;
            }
        }
    }

    if (!parsedSections || parsedSections.length === 0) {
        return (
            <div className="bg-app-bg-page rounded-lg p-4 text-xs font-mono text-app-text-label max-h-96 overflow-y-auto whitespace-pre-wrap border border-app-border-light">
                {markdown || '(No content available)'}
            </div>
        );
    }

    const activeSection = parsedSections[activeTabIndex] || parsedSections[0];

    return (
        <div className="space-y-3">
            {/* Tab Headers */}
            <div className="flex flex-wrap gap-2 border-b border-app-border-light pb-2">
                {parsedSections.map((section, index) => (
                    <button
                        key={index}
                        onClick={() => setActiveTabIndex(index)}
                        className={`px-3 py-1.5 text-xs font-medium rounded-t-lg transition-all ${activeTabIndex === index
                            ? 'bg-app-primary text-white border-b-2 border-app-primary'
                            : 'bg-app-bg-page text-app-text-label hover:bg-app-bg-card border border-app-border-light border-b-0'
                            }`}
                    >
                        {section.title || `Section ${index + 1}`}
                    </button>
                ))}
            </div>

            {/* Tab Content */}
            <div className="bg-app-bg-page rounded-lg p-4 text-xs font-mono text-app-text-label max-h-96 overflow-y-auto whitespace-pre-wrap border border-app-border-light">
                {activeSection.content || activeSection.markdown || '(No content)'}
            </div>
        </div>
    );
};


const parseAIResponse = (text, repoContext = null) => {
    let source = String(text || '').trim();
    source = source.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();
    source = source.replace(/<think>[\s\S]*/gi, '').trim();

    const hasExpectedShape = (obj) => obj && typeof obj === 'object' && !Array.isArray(obj)
        && ('questions' in obj || 'metrics' in obj || 'title' in obj || 'architecture' in obj);

    const tryParseObject = (value) => {
        try {
            const parsed = JSON.parse(value);
            return hasExpectedShape(parsed) ? parsed : null;
        } catch {
            return null;
        }
    };

    const fencedRegex = /```(?:json)?\s*([\s\S]*?)\s*```/gi;
    let fencedMatch;
    let lastValidFenced = null;
    let lastJsonLikeFence = null;
    while ((fencedMatch = fencedRegex.exec(source)) !== null) {
        const inner = fencedMatch[1].trim();
        if (inner.startsWith('{') && inner.endsWith('}')) {
            lastJsonLikeFence = { fullMatch: fencedMatch[0], index: fencedMatch.index };
        }
        const parsed = tryParseObject(inner);
        if (parsed) {
            lastValidFenced = { parsed, fullMatch: fencedMatch[0], index: fencedMatch.index };
        }
    }

    const forceMetricsType = (metricsObj) => {
        return metricsObj || null;
    };

    if (lastValidFenced) {
        const before = source.slice(0, lastValidFenced.index);
        const after = source.slice(lastValidFenced.index + lastValidFenced.fullMatch.length);
        const report = `${before}${after}`.trim();
        return {
            report,
            questions: lastValidFenced.parsed.questions || [],
            metrics: forceMetricsType(lastValidFenced.parsed.metrics),
            title: lastValidFenced.parsed.title || null,
            prerequisites: lastValidFenced.parsed.prerequisites || [],
            architecture: lastValidFenced.parsed.architecture || null
        };
    }

    if (lastJsonLikeFence) {
        const before = source.slice(0, lastJsonLikeFence.index);
        const after = source.slice(lastJsonLikeFence.index + lastJsonLikeFence.fullMatch.length);
        return {
            report: `${before}${after}`.trim(),
            questions: [],
            metrics: forceMetricsType(null),
            title: null,
            prerequisites: [],
            architecture: null
        };
    }

    const trimmed = source.trim().replace(/```+\s*$/g, '').trim();
    for (let i = trimmed.lastIndexOf('{'); i >= 0; i = trimmed.lastIndexOf('{', i - 1)) {
        const candidate = trimmed.slice(i).trim();
        const parsed = tryParseObject(candidate);
        if (parsed) {
            const report = trimmed.slice(0, i).trim();
            return {
                report,
                questions: parsed.questions || [],
                metrics: forceMetricsType(parsed.metrics),
                title: parsed.title || null,
                prerequisites: parsed.prerequisites || [],
                architecture: parsed.architecture || null
            };
        }
    }

    return {
        report: source,
        questions: [],
        metrics: forceMetricsType(null),
        title: null,
        prerequisites: [],
        architecture: null
    };
};

const buildRepoContextMeta = (context) => {
    if (!context) return null;
    const provider = String(context?.provider || 'github').trim().toLowerCase();
    const rawRepo = String(context?.repo || '').trim();
    if (!rawRepo) return null;

    if (provider === 'azure-devops') {
        const normalizedRepo = rawRepo.replace(/^\/+|\/+$/g, '');
        if (!normalizedRepo || normalizedRepo.split('/').filter(Boolean).length < 3) {
            return null;
        }
        return {
            repo: normalizedRepo,
            branch: String(context?.branch || '').trim() || null,
            source: 'link',
            provider: 'azure-devops',
            url: String(context?.url || '').trim() || null,
        };
    }

    const normalizedRepo = rawRepo
        .replace(/^https?:\/\/github\.com\//i, '')
        .replace(/\.git$/i, '')
        .replace(/^\/+|\/+$/g, '');

    if (!normalizedRepo || !normalizedRepo.includes('/')) {
        return null;
    }

    return {
        repo: normalizedRepo,
        branch: String(context?.branch || '').trim() || null,
        source: context?.fromLink ? 'link' : 'oauth',
        provider: 'github',
        url: `https://github.com/${normalizedRepo}.git`,
    };
};

const isLikelyHtml = (str) => {
    if (!str || typeof str !== 'string') return false;
    return /<[a-z][\s\S]*>/i.test(str);
};

const sanitizeHtml = (html) => {
    return DOMPurify.sanitize(html, {
        ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'a', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'div', 'span'],
        ALLOWED_ATTR: ['href', 'target', 'class', 'style'],
    });
};

// Utility to clear stale analysis flags from sessionStorage
const clearStaleAnalysisFlags = () => {
    const keysToRemove = [];
    for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        if (key && (key.startsWith('analysis_started_') || key === 'shouldStartAnalysis')) {
            keysToRemove.push(key);
        }
    }
    keysToRemove.forEach(key => sessionStorage.removeItem(key));
    console.log('Cleared stale analysis flags:', keysToRemove);
};

export default function AgentAnalysis({
    selectedProjectKey,
    projects = [],
    projectsLoading = false,
    fetchHistory
}) {
    const navigate = useNavigate();
    const location = useLocation();
    const token = localStorage.getItem('token');

    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [processing, setProcessing] = useState(false);
    const [progress, setProgress] = useState(0);
    const [progressMessage, setProgressMessage] = useState('');
    const [completedStages, setCompletedStages] = useState({});  // Track completed stages
    const [aiQuestions, setAiQuestions] = useState([]);
    const [userAnswers, setUserAnswers] = useState({});
    const [userFeedback, setUserFeedback] = useState('');
    const [governanceContext, setGovernanceContext] = useState(null);
    const [repoContext, setRepoContext] = useState(null);
    const [isSidebarOpen, setIsSidebarOpen] = useState(false); // Start closed by default
    const [sidebarTab, setSidebarTab] = useState('chat'); // 'chat' | 'clarification'
    const [analysisInProgress, setAnalysisInProgress] = useState(false); // Track if analysis is running
    const [selectedDocId, setSelectedDocId] = useState(null); // Selected revision document ID for checkpoints
    const [activeDesignTab, setActiveDesignTab] = useState('executive'); // 'executive' | 'hld' | 'lld'
    const [hldDesign, setHldDesign] = useState(null);
    const [lldDesign, setLldDesign] = useState(null);
    const [specStatus, setSpecStatus] = useState({ analysis_report: 'ready', hld: 'pending', lld: 'pending' });
    const [designLoading, setDesignLoading] = useState(false);
    const [designGenerating, setDesignGenerating] = useState(false);
    const [copiedSnippet, setCopiedSnippet] = useState(null);
    const [exportingPdfType, setExportingPdfType] = useState(null);

    // Concurrency guards for spec polling and design fetching
    const activeSpecsJobRef = useRef(null);
    const specsAbortControllerRef = useRef(null);
    const fetchedDocDesignIdRef = useRef(null);

    useEffect(() => {
        if (!result) {
            setHldDesign(null);
            setLldDesign(null);
            setSpecStatus({ analysis_report: 'ready', hld: 'pending', lld: 'pending' });
            return;
        }
        if (result.analysis?.hld) {
            const hld = result.analysis.hld;
            setHldDesign(hld?.markdown ? { ...hld, markdown: sanitizeDesignMarkdownDate(hld.markdown) } : hld);
        }
        if (result.analysis?.lld) {
            const lld = result.analysis.lld;
            setLldDesign(lld?.markdown ? { ...lld, markdown: sanitizeDesignMarkdownDate(lld.markdown) } : lld);
        }
        if (result.analysis?.spec_status) {
            setSpecStatus(result.analysis.spec_status);
        }
    }, [result?.id]);

    const listenForBackgroundSpecs = useCallback(async (jobId) => {
        if (!jobId || !token) return;
        // Singleton guard: if already polling this specific job, skip redundant call
        if (activeSpecsJobRef.current === jobId) {
            return;
        }
        if (specsAbortControllerRef.current) {
            specsAbortControllerRef.current.abort();
        }
        const abortController = new AbortController();
        specsAbortControllerRef.current = abortController;
        activeSpecsJobRef.current = jobId;

        try {
            const { pollArchitectureSpecs } = await import('../utils/analysisPolling');
            const finalSpecs = await pollArchitectureSpecs(
                jobId,
                token,
                (specsData) => {
                    if (abortController.signal.aborted) return;
                    if (specsData.spec_status) {
                        setSpecStatus(specsData.spec_status);
                    }
                    if (specsData.hld) {
                        const cleanHld = specsData.hld?.markdown ? { ...specsData.hld, markdown: sanitizeDesignMarkdownDate(specsData.hld.markdown) } : specsData.hld;
                        setHldDesign(cleanHld);
                        setResult(prev => prev ? {
                            ...prev,
                            analysis: {
                                ...(prev.analysis || {}),
                                hld: cleanHld,
                                spec_status: specsData.spec_status
                            }
                        } : prev);
                        if (resultCacheRef.current[selectedProjectKey]?.result?.analysis) {
                            resultCacheRef.current[selectedProjectKey].result.analysis.hld = cleanHld;
                            resultCacheRef.current[selectedProjectKey].result.analysis.spec_status = specsData.spec_status;
                        }
                    }
                    if (specsData.lld) {
                        const cleanLld = specsData.lld?.markdown ? { ...specsData.lld, markdown: sanitizeDesignMarkdownDate(specsData.lld.markdown) } : specsData.lld;
                        setLldDesign(cleanLld);
                        setResult(prev => prev ? {
                            ...prev,
                            analysis: {
                                ...(prev.analysis || {}),
                                lld: cleanLld,
                                spec_status: specsData.spec_status
                            }
                        } : prev);
                        if (resultCacheRef.current[selectedProjectKey]?.result?.analysis) {
                            resultCacheRef.current[selectedProjectKey].result.analysis.lld = cleanLld;
                            resultCacheRef.current[selectedProjectKey].result.analysis.spec_status = specsData.spec_status;
                        }
                    }
                },
                3000,
                120,
                abortController.signal
            );

            // When polling concludes, ensure lingering generating states are self-healed
            if (!abortController.signal.aborted) {
                setSpecStatus(prev => {
                    const updated = { ...prev };
                    if (updated.hld === 'generating' && !finalSpecs?.hld) {
                        updated.hld = 'pending';
                    }
                    if (updated.lld === 'generating' && !finalSpecs?.lld) {
                        updated.lld = 'pending';
                    }
                    return updated;
                });
            }
        } catch (e) {
            if (!abortController.signal.aborted) {
                console.warn('Failed to listen for background specs:', e);
                setSpecStatus(prev => ({
                    ...prev,
                    hld: prev.hld === 'generating' ? 'pending' : prev.hld,
                    lld: prev.lld === 'generating' ? 'pending' : prev.lld
                }));
            }
        } finally {
            if (activeSpecsJobRef.current === jobId) {
                activeSpecsJobRef.current = null;
            }
        }
    }, [token, selectedProjectKey]);

    const fetchArchitectureDesign = useCallback(async (docId) => {
        const targetId = docId || result?.id;
        if (!targetId) return;
        setDesignLoading(true);
        try {
            const res = await fetch(`${API_BASE_URL}/documents/${targetId}/design?auto_generate=false`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                let hasHld = false;
                let hasLld = false;
                if (data.hld) {
                    const hld = data.hld;
                    const cleanHld = hld?.markdown ? { ...hld, markdown: sanitizeDesignMarkdownDate(hld.markdown) } : hld;
                    setHldDesign(cleanHld);
                    hasHld = true;
                    setResult(prev => prev ? {
                        ...prev,
                        analysis: {
                            ...(prev.analysis || {}),
                            hld: cleanHld
                        }
                    } : prev);
                }
                if (data.lld) {
                    const lld = data.lld;
                    const cleanLld = lld?.markdown ? { ...lld, markdown: sanitizeDesignMarkdownDate(lld.markdown) } : lld;
                    setLldDesign(cleanLld);
                    hasLld = true;
                    setResult(prev => prev ? {
                        ...prev,
                        analysis: {
                            ...(prev.analysis || {}),
                            lld: cleanLld
                        }
                    } : prev);
                }
                if (data.spec_status) {
                    setSpecStatus(data.spec_status);
                }
                // Only reconnect background polling if the backend explicitly reports job_active is true!
                const activeJob = data.job_id || localStorage.getItem('active_specs_job_id');
                const isStillGenerating = Boolean(data.job_active) && (data.spec_status?.hld === 'generating' || data.spec_status?.lld === 'generating');
                if (activeJob && isStillGenerating) {
                    try {
                        localStorage.setItem('active_specs_job_id', activeJob);
                        if (selectedProjectKey) localStorage.setItem('active_specs_project_key', selectedProjectKey);
                    } catch (_) {}
                    listenForBackgroundSpecs(activeJob);
                } else if (!data.job_active) {
                    // Backend has no active job: clear active_specs_job_id from localStorage and reset generating to pending
                    try {
                        localStorage.removeItem('active_specs_job_id');
                        localStorage.removeItem('active_specs_project_key');
                    } catch (_) {}
                    setSpecStatus(prev => ({
                        ...prev,
                        hld: hasHld ? 'ready' : (prev.hld === 'generating' ? 'pending' : prev.hld),
                        lld: hasLld ? 'ready' : (prev.lld === 'generating' ? 'pending' : prev.lld)
                    }));
                }
            }
        } catch (err) {
            console.error('Failed to fetch architecture design:', err);
        } finally {
            setDesignLoading(false);
        }
    }, [result?.id, token, selectedProjectKey, listenForBackgroundSpecs]);

    useEffect(() => {
        const activeJobId = localStorage.getItem('active_specs_job_id') || result?._jobId || result?.analysis?._jobId;
        if (activeJobId && (!hldDesign || !lldDesign)) {
            listenForBackgroundSpecs(activeJobId);
        }
    }, [result?._jobId, result?.analysis?._jobId, listenForBackgroundSpecs]);

    useEffect(() => {
        if (result?.id && fetchedDocDesignIdRef.current !== result.id) {
            fetchedDocDesignIdRef.current = result.id;
            fetchArchitectureDesign(result.id);
        }
    }, [result?.id, fetchArchitectureDesign]);

    useEffect(() => {
        return () => {
            if (specsAbortControllerRef.current) {
                specsAbortControllerRef.current.abort();
                specsAbortControllerRef.current = null;
            }
            activeSpecsJobRef.current = null;
        };
    }, []);

    const handleRegenerateArchitectureDesign = async (type = 'all') => {
        if (!result?.id) return;
        setDesignGenerating(true);
        setSpecStatus(prev => ({
            ...prev,
            [type === 'all' ? 'hld' : type]: 'generating',
            ...(type === 'all' ? { lld: 'pending' } : {})
        }));
        try {
            const res = await fetch(`${API_BASE_URL}/documents/${result.id}/design/generate`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ design_type: type, force_regenerate: true })
            });
            if (res.ok) {
                const data = await res.json();
                if (data.hld) {
                    const hld = data.hld;
                    const cleanHld = hld?.markdown ? { ...hld, markdown: sanitizeDesignMarkdownDate(hld.markdown) } : hld;
                    setHldDesign(cleanHld);
                    setResult(prev => prev ? {
                        ...prev,
                        analysis: { ...(prev.analysis || {}), hld: cleanHld }
                    } : prev);
                }
                if (data.lld) {
                    const lld = data.lld;
                    const cleanLld = lld?.markdown ? { ...lld, markdown: sanitizeDesignMarkdownDate(lld.markdown) } : lld;
                    setLldDesign(cleanLld);
                    setResult(prev => prev ? {
                        ...prev,
                        analysis: { ...(prev.analysis || {}), lld: cleanLld }
                    } : prev);
                }
                if (data.spec_status) {
                    setSpecStatus(data.spec_status);
                }
            }
        } catch (err) {
            console.error('Failed to regenerate architecture design:', err);
            setSpecStatus(prev => ({
                ...prev,
                [type === 'all' ? 'hld' : type]: 'pending'
            }));
        } finally {
            setDesignGenerating(false);
        }
    };

    const handleDownloadArchitectureMarkdown = (type = 'hld') => {
        const design = type === 'lld' ? lldDesign : hldDesign;
        const content = sanitizeDesignMarkdownDate(design?.markdown || '');
        if (!content) return;
        const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const cleanProj = (result?.filename || 'Enterprise_System').replace(/[^a-zA-Z0-9_-]/g, '_');
        a.download = `${cleanProj}_${type.toUpperCase()}_Specification.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const handleDownloadArchitecturePDF = async (type = 'hld') => {
        if (exportingPdfType) return;
        const design = type === 'lld' ? lldDesign : hldDesign;
        const content = sanitizeDesignMarkdownDate(design?.markdown || '');
        if (!content) return;
        setExportingPdfType(type);
        try {
            await generateArchitectureDesignPDF({
                title: design.title || `${type.toUpperCase()} Specification`,
                documentType: type.toUpperCase(),
                markdownContent: content,
                projectName: result?.filename || 'Enterprise Solution',
                version: design.version || '1.0.0',
                renderMermaidToPng
            });
        } catch (err) {
            console.error('Failed to export architecture PDF:', err);
        } finally {
            setExportingPdfType(null);
        }
    };

    const handleCopyDdl = useCallback(() => {
        const content = lldDesign?.markdown || '';
        const match = content.match(/```sql([\s\S]*?)```/);
        const ddl = match ? match[1].trim() : content;
        navigator.clipboard.writeText(ddl);
        setCopiedSnippet('ddl');
        setTimeout(() => setCopiedSnippet(null), 2500);
    }, [lldDesign]);

    const handleSelectRevisionDoc = (doc) => {
        if (!doc || !doc.id) return;
        setSelectedDocId(doc.id);
        const docAnalysis = parseStoredDocumentAnalysis(doc);
        if (docAnalysis) {
            setAiQuestions(docAnalysis.questions || []);
            setUserAnswers(docAnalysis.userAnswers || {});
            setUserFeedback(docAnalysis.userFeedback || '');
            setCompletedStages(docAnalysis.stages || {});
            if (docAnalysis.hld) {
                const h = docAnalysis.hld;
                setHldDesign(h?.markdown ? { ...h, markdown: sanitizeDesignMarkdownDate(h.markdown) } : h);
            }
            if (docAnalysis.lld) {
                const l = docAnalysis.lld;
                setLldDesign(l?.markdown ? { ...l, markdown: sanitizeDesignMarkdownDate(l.markdown) } : l);
            }
            setResult({
                id: doc.id,
                filename: doc.filename,
                extraction: {
                    markdown: doc.full_content || '',
                    html: '',
                    num_pages: null,
                    sections: docAnalysis.sections || [],
                },
                analysis: docAnalysis,
                revisionNumber: doc.revision_number || docAnalysis.projectMeta?.revision_number || 1,
            });
        }
    };

    // Helper to extract virtual revisions if documents were concatenated in single DB row
    const getProcessedProjectDocuments = useCallback((project) => {
        if (!project || !project.documents || project.documents.length === 0) return [];

        let processed = [];

        project.documents.forEach((doc, docIdx) => {
            const content = doc.full_content || '';
            const markerRegex = /---\s*(?:NEW\s+)?REVISION\s+(\d+)\s*-\s*([^\n]+)\s*---/gi;

            let matches = [];
            let match;
            while ((match = markerRegex.exec(content)) !== null) {
                matches.push({
                    revNum: parseInt(match[1], 10),
                    title: match[2].replace(/\s*\([^)]*\)/g, '').trim(),
                    startIndex: match.index
                });
            }

            if (matches.length > 1) {
                matches.sort((a, b) => a.revNum - b.revNum);

                matches.forEach((curr, idx) => {
                    const next = matches[idx + 1];
                    const secContent = content.substring(
                        curr.startIndex,
                        next ? next.startIndex : content.length
                    );

                    const parsedAnalysis = parseStoredDocumentAnalysis(doc);

                    processed.push({
                        id: `${doc.id}_rev_${curr.revNum}`,
                        real_db_id: doc.id,
                        filename: curr.title || `Revision ${curr.revNum}`,
                        full_content: secContent,
                        content_preview: secContent.substring(0, 200),
                        analysis_result: doc.analysis_result,
                        revision_number: curr.revNum,
                        projectMeta: {
                            ...(parsedAnalysis?.projectMeta || {}),
                            revision_number: curr.revNum,
                        }
                    });
                });
            } else {
                const parsedAnalysis = parseStoredDocumentAnalysis(doc);
                processed.push({
                    ...doc,
                    revision_number: parsedAnalysis?.projectMeta?.revision_number || docIdx + 1,
                });
            }
        });

        // Deduplicate by revision_number if present
        const revMap = new Map();
        processed.forEach(d => {
            const revKey = d.revision_number || d.id;
            revMap.set(revKey, d);
        });

        return Array.from(revMap.values()).sort((a, b) => (a.revision_number || 0) - (b.revision_number || 0));
    }, []);

    // Chat-based update history state
    const [chatMessages, setChatMessages] = useState([]); // [{id, role, content, timestamp, changeSummary, affectedSections}]
    const [chatInput, setChatInput] = useState('');
    const [chatSending, setChatSending] = useState(false);
    const chatEndRef = useRef(null);

    // Dynamic requirements elicitation techniques states
    const [elicitationTechniques, setElicitationTechniques] = useState([]);
    const [techniquesLoading, setTechniquesLoading] = useState(false);
    const [techniquesError, setTechniquesError] = useState('');
    const [techniquesSource, setTechniquesSource] = useState('ai_generated'); // 'uploaded' | 'ai_generated' | 'static_fallback'
    const [discussMode, setDiscussMode] = useState(false);
    const [modeDropdownOpen, setModeDropdownOpen] = useState(false);
    const [isChatExpanded, setIsChatExpanded] = useState(false);

    // Close the mode dropdown selector on click outside
    useEffect(() => {
        if (!modeDropdownOpen) return;
        const handleOutsideClick = (e) => {
            if (!e.target.closest('.mode-dropdown-container')) {
                setModeDropdownOpen(false);
            }
        };
        document.addEventListener('click', handleOutsideClick);
        return () => document.removeEventListener('click', handleOutsideClick);
    }, [modeDropdownOpen]);

    // Cache results by project key to prevent data loss when switching projects
    const resultCacheRef = useRef({});
    const lastLoadedProjectRef = useRef(null);
    const activeJobIdRef = useRef(null);

    const selectedProject = projects.find((p) => p.key === selectedProjectKey) || null;
    const hasGovernanceAssessment = Boolean(selectedProject?.governanceResultId || governanceContext?.result_id);

    // CRITICAL FIX: Read project token from URL parameter if present
    // This ensures the correct project is loaded after navigation from GovernanceResult
    useEffect(() => {
        const params = new URLSearchParams(location.search);
        const projectFromUrl = params.get('project');
        
        if (projectFromUrl && projectFromUrl !== selectedProjectKey) {
            console.log('Project token from URL parameter:', projectFromUrl);
            // Update localStorage to persist the selection
            // The parent component (AppLayout) will read this and update selectedProjectKey
            try {
                localStorage.setItem('status_dashboard_selected_project_key', projectFromUrl);
                // Trigger a page reload to let AppLayout pick up the new project
                window.location.href = '/agent-analysis';
            } catch (e) {
                console.warn('Failed to save project key to localStorage:', e);
            }
        }
    }, [location.search, selectedProjectKey]);

    // CRITICAL FIX: Update cache whenever state changes for the current project
    useEffect(() => {
        if (selectedProjectKey && result && selectedProjectKey === lastLoadedProjectRef.current) {
            resultCacheRef.current[selectedProjectKey] = {
                result,
                aiQuestions,
                userAnswers,
                userFeedback,
                completedStages,
                chatMessages,
            };
        }
    }, [selectedProjectKey, result, aiQuestions, userAnswers, userFeedback, completedStages, chatMessages]);

    // Sync governance context and repo context dynamically when selectedProjectKey changes
    useEffect(() => {
        if (!selectedProjectKey) {
            setGovernanceContext(null);
            setRepoContext(null);
            return;
        }

        const syncContexts = async () => {
            let govCtxLoaded = false;
            let repoCtxLoaded = false;

            // 1. Try to extract from the selected project's latest document analysis
            if (selectedProject?.latestDocument) {
                try {
                    const parsedAnalysis = parseStoredDocumentAnalysis(selectedProject.latestDocument);
                    if (parsedAnalysis?.governanceContext) {
                        setGovernanceContext(parsedAnalysis.governanceContext);
                        govCtxLoaded = true;
                    }
                    if (parsedAnalysis?.repoContextMeta) {
                        setRepoContext(parsedAnalysis.repoContextMeta);
                        repoCtxLoaded = true;
                    }
                } catch (e) {
                    console.warn('Failed to parse contexts from latest document:', e);
                }
            }

            // 2. If governance context was not in document, fetch from governance API
            if (!govCtxLoaded && (selectedProject?.governanceResultId || selectedProjectKey)) {
                try {
                    const identifier = selectedProject?.governanceResultId || selectedProjectKey;
                    const res = await fetch(`${API_BASE_URL}/governance/result/${identifier}`, {
                        headers: { Authorization: `Bearer ${token}` }
                    });
                    if (res.ok) {
                        const data = await res.json();
                        if (data && data.id) {
                            const normalizedDimensionScores = {
                                business_value: data.dimension_scores?.business_value ?? 0,
                                data_sensitivity: data.dimension_scores?.data_sensitivity ?? 0,
                                integration_complexity: data.dimension_scores?.integration_complexity ?? 0,
                                operational_impact: data.dimension_scores?.operational_impact ?? 0,
                                ai_risk: data.dimension_scores?.ai_risk ?? 0,
                                ownership: data.dimension_scores?.ownership ?? 0,
                            };
                            const formattedAnswers = Array.isArray(data.answers)
                                ? data.answers.map((answer) => ({
                                    question_id: answer.question_id,
                                    score: answer.score,
                                    selected_option: answer.selected_option || '',
                                }))
                                : [];
                            const fallbackDesc = (cls) => {
                                if (cls === 'SANDBOX') return 'Sandbox Approved - Low governance required';
                                if (cls === 'CONTROLLED_SANDBOX') return 'Controlled Sandbox (Fusion) - Standard template required';
                                if (cls === 'ENTERPRISE') return 'Enterprise Build - Full IT oversight required';
                                return 'Governance classification unavailable';
                            };
                            
                            const govCtx = {
                                project_name: data.project_name || '',
                                result_id: data.id || null,
                                submission_date: data.submission_date,
                                classification: data.classification,
                                classification_description: data.classification_description || fallbackDesc(data.classification),
                                weighted_score: data.weighted_score,
                                recommendation: data.recommendation,
                                hard_stops: data.hard_stops || [],
                                answers: formattedAnswers,
                                dimension_scores: normalizedDimensionScores,
                            };
                            setGovernanceContext(govCtx);
                            govCtxLoaded = true;
                        }
                    }
                } catch (e) {
                    console.warn('Failed to fetch governance context for project:', e);
                }
            }

            // 3. If repo context was not in document, fetch from git-config API
            if (!repoCtxLoaded) {
                try {
                    const configRes = await fetch(`${API_BASE_URL}/api/projects/${selectedProjectKey}/git-config`, {
                        headers: { Authorization: `Bearer ${token}` }
                    });
                    if (configRes.ok) {
                        const configData = await configRes.json();
                        if (configData && configData.source_repo_url) {
                            setRepoContext({
                                repo: configData.source_repo_url,
                                provider: (configData.source_repo_url.includes('dev.azure.com') || configData.source_repo_url.includes('visualstudio.com')) ? 'azure-devops' : 'github',
                                context: ''
                            });
                            repoCtxLoaded = true;
                        }
                    }
                } catch (e) {
                    console.warn('Failed to fetch git-config for project:', e);
                }
            }

            // Fallback: If absolutely nothing found, load from sessionStorage as a last resort
            if (!govCtxLoaded) {
                const storedContext = sessionStorage.getItem('governanceContext') || localStorage.getItem('governanceContext');
                if (storedContext) {
                    try {
                        setGovernanceContext(JSON.parse(storedContext));
                    } catch { }
                } else {
                    setGovernanceContext(null);
                }
            }
            if (!repoCtxLoaded) {
                const storedRepoContext = sessionStorage.getItem('repoContext') || localStorage.getItem('repoContext');
                if (storedRepoContext) {
                    try {
                        setRepoContext(JSON.parse(storedRepoContext));
                    } catch { }
                } else {
                    setRepoContext(null);
                }
            }
        };

        syncContexts();
    }, [selectedProjectKey, selectedProject, projects, token]);

    const persistHistoryDocument = useCallback(async (payload, documentId = null) => {
        const response = await fetch(
            documentId ? API_ENDPOINTS.HISTORY_ITEM(documentId) : API_ENDPOINTS.HISTORY,
            {
                method: documentId ? 'PUT' : 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`
                },
                body: JSON.stringify(payload)
            }
        );

        if (response.status === 401) {
            return null;
        }

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || 'History save failed');
        }

        return response.json();
    }, [token]);

    const saveToHistory = useCallback(async (newResult, taskKey = selectedProjectKey, analysisRepoContext = repoContext) => {
        if (!newResult?.filename) return;

        try {
            const project = projects.find((p) => p.key === taskKey);
            const currentRevisionCount = project?.documents?.length || 0;
            const hasExistingDocument = Boolean(newResult?.id);
            const nextRevisionNumber = newResult?.revisionNumber
                || (hasExistingDocument ? Math.max(currentRevisionCount, 1) : currentRevisionCount + 1);
            const repoContextMeta = newResult?.analysis?.repoContextMeta || buildRepoContextMeta(analysisRepoContext);
            const effectiveJobId = newResult?._jobId || newResult?.analysis?._jobId || localStorage.getItem('active_specs_job_id') || localStorage.getItem('active_analysis_job_id') || null;
            const storedAnalysis = {
                ...(newResult.analysis || {}),
                _jobId: effectiveJobId,
                hld: newResult?.analysis?.hld || hldDesign || null,
                lld: newResult?.analysis?.lld || lldDesign || null,
                spec_status: newResult?.analysis?.spec_status || specStatus || null,
                governanceContext: governanceContext || null,
                repoContextMeta: repoContextMeta || null,
                stages: (completedStages && Object.keys(completedStages).length > 0)
                    ? completedStages
                    : (newResult?.analysis?.stages || {}),  // Preserve existing analysis stages
                sections: newResult.extraction?.sections || [],  // Preserve all input tab sections
                projectMeta: {
                    project_name: project?.name || governanceContext?.project_name || 'Project',
                    project_token: project?.projectToken || taskKey || null,
                    governance_result_id: governanceContext?.result_id || project?.governanceResultId || null,
                    revision_number: nextRevisionNumber,
                    revision_reason: null,
                    repo_context: repoContextMeta || null,
                }
            };

            const savedDoc = await persistHistoryDocument({
                filename: newResult.filename,
                content_preview: `${newResult.extraction?.markdown?.substring(0, 200) || ''}...`,
                full_content: newResult.extraction?.markdown,
                analysis_result: JSON.stringify(storedAnalysis)
            }, newResult?.id || null);

            if (savedDoc) {
                setResult(prev => ({ ...prev, id: savedDoc.id, revisionNumber: nextRevisionNumber }));

                // CRITICAL FIX: Update cache when data is saved
                if (resultCacheRef.current[taskKey]) {
                    resultCacheRef.current[taskKey].result = {
                        ...resultCacheRef.current[taskKey].result,
                        id: savedDoc.id,
                        revisionNumber: nextRevisionNumber
                    };
                }

                if (fetchHistory) fetchHistory();
            }
        } catch (e) {
            console.error('History save failed', e);
        }
    }, [selectedProjectKey, projects, governanceContext, repoContext, completedStages, persistHistoryDocument, fetchHistory]);

    const fetchAnalysis = useCallback(async (
        payload,
        token,
        initialContext = null,
        analysisOptions = {}
    ) => {
        try {
            setError('');
            const docId = (initialContext || result)?.id;
            if (docId) {
                sessionStorage.removeItem(`analysis_error_${docId}`);
            }
            // Import polling utilities
            const { startAndPollAnalysis } = await import('../utils/analysisPolling');

            // Start analysis with polling
            const data = await startAndPollAnalysis(
                payload,
                token,
                (progress, message, stages) => {
                    // Update progress in UI
                    setProgress(progress);
                    setProgressMessage(message);
                    // Update completed stages
                    if (stages && Object.keys(stages).length > 0) {
                        setCompletedStages(stages);
                    }
                },
                5000, // Poll every 5 seconds
                720,   // Max 60 minutes (720 * 5s = 3600s)
                selectedProjectKey
            );

            // For targeted updates, the backend returns metrics/questions/architecture directly
            // alongside the patched report. Merge these with existing data.
            const isTargetedUpdate = Boolean(data.update_type || data.change_summary);
            const existingAnalysis = (initialContext || result)?.analysis || {};
            const effectiveRepoContext = analysisOptions.repoContext || repoContext || null;

            const { report: parsedReport, questions: parsedQuestions, metrics: parsedMetrics,
                title, prerequisites: parsedPrereqs, architecture: parsedArch } = parseAIResponse(data.analysis || '', effectiveRepoContext);

            const report = parsedReport;
            // For targeted updates, prefer backend-returned data (already merged with previous)
            const questions = isTargetedUpdate
                ? (data.questions?.length > 0 ? data.questions : (parsedQuestions.length > 0 ? parsedQuestions : existingAnalysis.questions || []))
                : parsedQuestions;
            const metrics = isTargetedUpdate
                ? (Object.keys(data.metrics || {}).length > 0 ? data.metrics : (parsedMetrics || existingAnalysis.metrics))
                : parsedMetrics;
            const prerequisites = isTargetedUpdate
                ? (data.prerequisites?.length > 0 ? data.prerequisites : (parsedPrereqs.length > 0 ? parsedPrereqs : existingAnalysis.prerequisites || []))
                : parsedPrereqs;
            const architecture = isTargetedUpdate
                ? (data.architecture && Object.keys(data.architecture).length > 0 ? data.architecture : (parsedArch || existingAnalysis.architecture))
                : parsedArch;

            if (questions.length > 0) setAiQuestions(questions);

            const effectiveGovernanceContext = analysisOptions.governanceContext || governanceContext || null;
            const finalFilename = title || (initialContext || result)?.filename;

            const finalResult = {
                ...(initialContext || result),
                filename: finalFilename,
                analysis: {
                    ...existingAnalysis,  // Preserve all existing analysis fields
                    ...data,
                    analysis: report,
                    questions: questions,
                    metrics: metrics,
                    prerequisites: prerequisites,
                    architecture: architecture,
                    userAnswers: userAnswers,
                    userFeedback: userFeedback,
                    governanceContext: effectiveGovernanceContext,
                    repoContextMeta: buildRepoContextMeta(effectiveRepoContext),
                    // Store change metadata for chat display
                    change_summary: data.change_summary || null,
                    affected_sections: data.affected_sections || [],
                    // Merge updated stages (from targeted update) preserving previous
                    stages: isTargetedUpdate && data.stages
                        ? { ...(existingAnalysis.stages || {}), ...data.stages }
                        : (data.stages || existingAnalysis.stages || ((completedStages && Object.keys(completedStages).length > 0) ? completedStages : {})),
                }
            };

            // Persist the detected project type to localStorage and DB
            const pt = metrics?.project_type || data.project_type || existingAnalysis.metrics?.project_type;
            if (pt && selectedProjectKey) {
                const normalizedPt = String(pt).toLowerCase();
                localStorage.setItem(`project_type_${selectedProjectKey}`, normalizedPt);
                fetch(`${API_BASE_URL}/api/agent/projects/${selectedProjectKey}/project-type`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({ project_type: normalizedPt })
                }).catch(err => console.error("Failed to save project type from analysis:", err));
            }

            if (finalResult.analysis?.stages && Object.keys(finalResult.analysis.stages).length > 0) {
                setCompletedStages(finalResult.analysis.stages);
            }

            if (finalResult.analysis?.hld) setHldDesign(finalResult.analysis.hld);
            if (finalResult.analysis?.lld) setLldDesign(finalResult.analysis.lld);

            setResult(finalResult);
            setProgress(100);
            setProgressMessage('Analysis complete!');
            await saveToHistory(finalResult, selectedProjectKey, effectiveRepoContext);
            const activeJobId = finalResult?._jobId || data?._jobId;
            if (activeJobId && (!finalResult.analysis?.hld || !finalResult.analysis?.lld)) {
                try {
                    localStorage.setItem('active_specs_job_id', activeJobId);
                    if (selectedProjectKey) localStorage.setItem('active_specs_project_key', selectedProjectKey);
                } catch (_) {}
                listenForBackgroundSpecs(activeJobId);
            }
            const completedDocId = finalResult?.id || (initialContext || result)?.id;
            if (completedDocId) {
                sessionStorage.removeItem(`analysis_started_${completedDocId}`);
                sessionStorage.removeItem(`analysis_error_${completedDocId}`);
            }
            return finalResult;
        } catch (err) {
            console.error('Analysis error:', err);
            const userFriendlyError = formatAnalysisError(err);
            setError(`Analysis Error: ${userFriendlyError}`);
            sessionStorage.setItem(`analysis_error_${(initialContext || result)?.id}`, `Analysis Error: ${userFriendlyError}`);
            setProgress(0);
            setProgressMessage('');
            setCompletedStages({});  // Clear stages on error
            setProcessing(false);  // Stop showing the loader
            setAnalysisInProgress(false);  // Clear the in-progress flag
            throw err;
        } finally {
            setProcessing(false);  // Ensure processing is stopped
            setAnalysisInProgress(false);  // Ensure flag is cleared
        }
    }, [governanceContext, repoContext, userAnswers, userFeedback, result, selectedProjectKey, saveToHistory]);

    const resumeAnalysisPolling = useCallback(async (jobId, initialResult, options = {}) => {
        if (activeJobIdRef.current === jobId) {
            console.log('Already polling this job, skipping duplicate invocation');
            return;
        }
        activeJobIdRef.current = jobId;

        if (!token) {
            setError('You are not logged in. Please login again.');
            activeJobIdRef.current = null;
            return;
        }

        setAnalysisInProgress(true);
        setProcessing(true);
        setLoading(false);
        setError('');
        if (initialResult?.id) {
            sessionStorage.removeItem(`analysis_error_${initialResult.id}`);
        }
        setProgress(0);
        setProgressMessage('Connecting to background analysis job...');
        
        if (initialResult) {
            setResult(initialResult);
        }

        try {
            const { pollUntilComplete } = await import('../utils/analysisPolling');
            const data = await pollUntilComplete(
                jobId,
                token,
                (progress, message, stages) => {
                    setProgress(progress);
                    setProgressMessage(message);
                    if (stages && Object.keys(stages).length > 0) {
                        setCompletedStages(stages);
                    }
                },
                5000, // Poll every 5 seconds
                720   // Max 60 minutes (720 * 5s = 3600s)
            );

            const isTargetedUpdate = Boolean(data.update_type || data.change_summary);
            const existingAnalysis = (initialResult || result)?.analysis || {};
            const effectiveRepoContext = options.repoContext || repoContext || null;

            const { report: parsedReport, questions: parsedQuestions, metrics: parsedMetrics,
                title, prerequisites: parsedPrereqs, architecture: parsedArch } = parseAIResponse(data.analysis || '', effectiveRepoContext);

            const report = parsedReport;
            const questions = isTargetedUpdate
                ? (data.questions?.length > 0 ? data.questions : (parsedQuestions.length > 0 ? parsedQuestions : existingAnalysis.questions || []))
                : parsedQuestions;
            const metrics = isTargetedUpdate
                ? (Object.keys(data.metrics || {}).length > 0 ? data.metrics : (parsedMetrics || existingAnalysis.metrics))
                : parsedMetrics;
            const prerequisites = isTargetedUpdate
                ? (data.prerequisites?.length > 0 ? data.prerequisites : (parsedPrereqs.length > 0 ? parsedPrereqs : existingAnalysis.prerequisites || []))
                : parsedPrereqs;
            const architecture = isTargetedUpdate
                ? (data.architecture && Object.keys(data.architecture).length > 0 ? data.architecture : (parsedArch || existingAnalysis.architecture))
                : parsedArch;

            if (questions.length > 0) setAiQuestions(questions);

            const finalResult = {
                ...(initialResult || result),
                filename: title || (initialResult || result)?.filename,
                analysis: {
                    ...existingAnalysis,
                    ...data,
                    analysis: report,
                    questions: questions,
                    metrics: metrics,
                    prerequisites: prerequisites,
                    architecture: architecture,
                    userAnswers: userAnswers,
                    userFeedback: userFeedback,
                    governanceContext: options.governanceContext || governanceContext || null,
                    repoContextMeta: buildRepoContextMeta(effectiveRepoContext),
                    change_summary: data.change_summary || null,
                    affected_sections: data.affected_sections || [],
                    stages: isTargetedUpdate && data.stages
                        ? { ...(existingAnalysis.stages || {}), ...data.stages }
                        : (data.stages || existingAnalysis.stages || ((completedStages && Object.keys(completedStages).length > 0) ? completedStages : {})),
                }
            };

            const pt = metrics?.project_type || data.project_type || existingAnalysis.metrics?.project_type;
            if (pt && selectedProjectKey) {
                const normalizedPt = String(pt).toLowerCase();
                localStorage.setItem(`project_type_${selectedProjectKey}`, normalizedPt);
                fetch(`${API_BASE_URL}/api/agent/projects/${selectedProjectKey}/project-type`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({ project_type: normalizedPt })
                }).catch(err => console.error("Failed to save project type from analysis:", err));
            }

            if (finalResult.analysis?.stages && Object.keys(finalResult.analysis.stages).length > 0) {
                setCompletedStages(finalResult.analysis.stages);
            }

            if (finalResult.analysis?.hld) setHldDesign(finalResult.analysis.hld);
            if (finalResult.analysis?.lld) setLldDesign(finalResult.analysis.lld);

            setResult(finalResult);
            setProgress(100);
            setProgressMessage('Analysis complete!');
            await saveToHistory(finalResult, selectedProjectKey, effectiveRepoContext);
            if (jobId && (!finalResult.analysis?.hld || !finalResult.analysis?.lld)) {
                try {
                    localStorage.setItem('active_specs_job_id', jobId);
                    if (selectedProjectKey) localStorage.setItem('active_specs_project_key', selectedProjectKey);
                } catch (_) {}
                listenForBackgroundSpecs(jobId);
            }
            const completedDocId = finalResult?.id || initialResult?.id;
            if (completedDocId) {
                sessionStorage.removeItem(`analysis_started_${completedDocId}`);
                sessionStorage.removeItem(`analysis_error_${completedDocId}`);
            }
            
            // Clean up localStorage keys
            localStorage.removeItem('active_analysis_job_id');
            localStorage.removeItem('active_analysis_project_key');
        } catch (err) {
            console.error('Resumed analysis polling error:', err);
            const userFriendlyError = formatAnalysisError(err);
            setError(`Analysis Error: ${userFriendlyError}`);
            sessionStorage.setItem(`analysis_error_${initialResult?.id}`, `Analysis Error: ${userFriendlyError}`);
            setProgress(0);
            setProgressMessage('');
            setCompletedStages({});
            
            // Clean up localStorage keys on error
            localStorage.removeItem('active_analysis_job_id');
            localStorage.removeItem('active_analysis_project_key');
        } finally {
            setProcessing(false);
            setAnalysisInProgress(false);
            activeJobIdRef.current = null;
        }
    }, [token, result, repoContext, governanceContext, userAnswers, userFeedback, selectedProjectKey, saveToHistory]);

    const streamAnalysis = useCallback(async (
        payload,
        token,
        initialContext = null,
        analysisOptions = {}
    ) => {
        const effectiveRepoContext = analysisOptions.repoContext || repoContext || null;
        try {
            setError('');
            const docId = (initialContext || result)?.id;
            if (docId) {
                sessionStorage.removeItem(`analysis_error_${docId}`);
            }
            const response = await fetch(API_ENDPOINTS.AI_ANALYZE, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify(payload)
            });

            if (response.status === 401) {
                return;
            }

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                if (response.status === 403 && (errData.detail === 'CROSS_TENANT_PROJECT_ACCESS_DENIED' || (typeof errData.detail === 'string' && errData.detail.includes('CROSS_TENANT_PROJECT_ACCESS_DENIED')))) {
                    localStorage.removeItem('status_dashboard_selected_project_key');
                    throw new Error('Project belongs to another organization. Please select a valid project.');
                }
                throw new Error(errData.detail || 'Analysis stream failed');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let aiText = '';
            let aiReasoning = '';
            let buffer = '';

            setProgress(0);
            setProgressMessage('Generating comprehensive Agent Action Plan... This may take up to 10 minutes.');

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');

                buffer = lines.pop() || '';

                for (const line of lines) {
                    const trimmedLine = line.trim();
                    if (!trimmedLine || !trimmedLine.startsWith('data: ')) continue;

                    const dataStr = trimmedLine.slice(6);
                    if (dataStr === '[DONE]') continue;

                    try {
                        const data = JSON.parse(dataStr);
                        if (data.choices && data.choices.length > 0) {
                            const delta = data.choices[0].delta || {};

                            if (delta.reasoning_content) {
                                aiReasoning += delta.reasoning_content;
                            }

                            if (delta.content) {
                                aiText += delta.content;
                            }

                            const { report, questions, metrics, prerequisites, architecture } = parseAIResponse(aiText, effectiveRepoContext);
                            if (questions.length > 0) setAiQuestions(questions);

                            setResult(prev => ({
                                ...(prev || initialContext),
                                analysis: {
                                    ...(prev?.analysis || {}),
                                    analysis: report,
                                    reasoning: aiReasoning,
                                    model: payload.model || 'Streaming...',
                                    metrics: metrics,
                                    prerequisites: prerequisites,
                                    architecture: architecture
                                }
                            }));
                        }
                    } catch (e) {
                        console.warn('Error parsing stream chunk', e);
                    }
                }
            }

            const { report, questions, metrics, title, prerequisites, architecture } = parseAIResponse(aiText, effectiveRepoContext);

            if (!architecture && !analysisOptions.forceArchitectureRetry) {
                setProgress(92);
                setProgressMessage('Finalizing user flow diagram...');
                await fetchAnalysisRef.current(
                    { ...payload, stream: false },
                    token,
                    initialContext || result,
                    { ...analysisOptions, forceArchitectureRetry: true }
                );
                return;
            }

            const effectiveGovernanceContext = analysisOptions.governanceContext || governanceContext || null;
            const effectiveRepoContext = analysisOptions.repoContext || repoContext || null;
            const finalFilename = title || (initialContext || result)?.filename;

            const existingAnalysis = (initialContext || result)?.analysis || {};
            const finalResult = {
                ...(initialContext || result),
                filename: finalFilename,
                analysis: {
                    ...existingAnalysis,
                    analysis: report,
                    questions: questions,
                    metrics: metrics,
                    prerequisites: prerequisites,
                    architecture: architecture,
                    userAnswers: userAnswers,
                    userFeedback: userFeedback,
                    governanceContext: effectiveGovernanceContext,
                    repoContextMeta: buildRepoContextMeta(effectiveRepoContext),
                    reasoning: aiReasoning,
                    model: payload.model || 'Streaming...',
                    stages: (existingAnalysis.stages && Object.keys(existingAnalysis.stages).length > 0)
                        ? existingAnalysis.stages
                        : ((completedStages && Object.keys(completedStages).length > 0) ? completedStages : {}),
                }
            };

            // Persist the detected project type to localStorage and DB
            const pt = metrics?.project_type || finalResult.analysis.metrics?.project_type;
            if (pt && selectedProjectKey) {
                const normalizedPt = String(pt).toLowerCase();
                localStorage.setItem(`project_type_${selectedProjectKey}`, normalizedPt);
                fetch(`${API_BASE_URL}/api/agent/projects/${selectedProjectKey}/project-type`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({ project_type: normalizedPt })
                }).catch(err => console.error("Failed to save project type from stream analysis:", err));
            }

            if (finalResult.analysis?.hld) setHldDesign(finalResult.analysis.hld);
            if (finalResult.analysis?.lld) setLldDesign(finalResult.analysis.lld);

            setResult(finalResult);
            setProgress(100);
            setProgressMessage('Analysis complete!');
            setAiQuestions(questions?.length ? questions : []);
            await saveToHistory(finalResult, selectedProjectKey, effectiveRepoContext);
            const completedDocId = finalResult?.id || (initialContext || result)?.id;
            if (completedDocId) {
                sessionStorage.removeItem(`analysis_started_${completedDocId}`);
                sessionStorage.removeItem(`analysis_error_${completedDocId}`);
            }
        } catch (err) {
            const userFriendlyError = formatAnalysisError(err);
            setError(`Stream Error: ${userFriendlyError}`);
            sessionStorage.setItem(`analysis_error_${(initialContext || result)?.id}`, `Stream Error: ${userFriendlyError}`);
        }
    }, [governanceContext, repoContext, userAnswers, userFeedback, result, selectedProjectKey, saveToHistory]);

    const fetchAnalysisRef = useRef(fetchAnalysis);
    const streamAnalysisRef = useRef(streamAnalysis);
    const resumeAnalysisPollingRef = useRef(resumeAnalysisPolling);
    fetchAnalysisRef.current = fetchAnalysis;
    streamAnalysisRef.current = streamAnalysis;
    resumeAnalysisPollingRef.current = resumeAnalysisPolling;

    const handleRepositoryOnlyAnalysis = useCallback(async () => {
        if (!token) {
            setError('You are not logged in. Please login again.');
            setLoading(false);
            return;
        }

        // Prevent duplicate analysis
        if (analysisInProgress) {
            console.log('Repository analysis already in progress, skipping...');
            return;
        }

        setAnalysisInProgress(true);
        setProcessing(true);
        setLoading(false);
        setProgress(0);
        setProgressMessage('Initializing repository analysis...');
        setError('');
        setAiQuestions([]);
        setUserAnswers({});
        setUserFeedback('');

        try {
            // Create a virtual document entry for the repository analysis
            const virtualDocument = {
                id: `repo-${selectedProjectKey}-${Date.now()}`,
                filename: `Repository Analysis - ${repoContext.repo || 'Unknown Repository'}`,
                full_content: repoContext.context,
                content_preview: repoContext.context?.substring(0, 200) + '...' || '',
            };

            const initialResult = {
                id: virtualDocument.id,
                filename: virtualDocument.filename,
                extraction: {
                    markdown: repoContext.context,
                    html: '',
                    num_pages: null,
                },
                analysis: { analysis: '', reasoning: '' },
                revisionNumber: 1,
                isRepositoryOnly: true, // Flag to indicate this is repo-only analysis
            };

            setResult(initialResult);

            // Get AI config from localStorage
            const aiConfigStr = localStorage.getItem('aiConfig');
            let aiConfig = { apiUrl: '', apiKey: '', model: '', stream: false };
            if (aiConfigStr) {
                try {
                    aiConfig = JSON.parse(aiConfigStr);
                } catch { }
            }

            const aiPayload = {
                document_content: repoContext.context,
                api_url: aiConfig?.apiUrl || undefined,
                api_key: aiConfig?.apiKey || undefined,
                model: aiConfig?.model || undefined,
                stream: aiConfig?.stream || false,
                governance_context: governanceContext || undefined,
            };

            if (aiConfig?.stream || false) {
                await streamAnalysisRef.current(aiPayload, token, initialResult, {
                    repoContext: repoContext,
                    governanceContext: governanceContext,
                });
            } else {
                setProgress(0);
                setProgressMessage('Submitting repository analysis request...');
                await fetchAnalysisRef.current(aiPayload, token, initialResult, {
                    repoContext: repoContext,
                    governanceContext: governanceContext,
                });
            }
        } catch (err) {
            const userFriendlyError = formatAnalysisError(err);
            setError(userFriendlyError || 'Repository analysis failed.');
        } finally {
            setProcessing(false);
            setAnalysisInProgress(false);
        }
    }, [token, governanceContext, selectedProjectKey, repoContext, fetchAnalysisRef, streamAnalysisRef, analysisInProgress]);

    const triggerPendingAnalysis = useCallback(async (document, pendingAnalysis) => {
        if (!token) {
            setError('You are not logged in. Please login again.');
            setLoading(false);
            return;
        }

        // Prevent duplicate analysis
        if (analysisInProgress) {
            console.log('Analysis already in progress, skipping...');
            return;
        }

        setAnalysisInProgress(true);
        setProcessing(true);
        setLoading(false);
        setProgress(0);
        setProgressMessage('Governance completed. Initializing Agent Analysis...');
        setError('');
        setAiQuestions([]);
        setUserAnswers({});
        setUserFeedback('');

        try {
            const pendingRepoContext = pendingAnalysis?.repoContextState || null;
            const effectiveGovernanceContext = governanceContext || pendingAnalysis?.governanceContext || null;

            setRepoContext(pendingRepoContext);

            const initialResult = {
                id: document.id,
                filename: document.filename,
                extraction: {
                    markdown: document.full_content,
                    html: '',
                    num_pages: null,
                    sections: pendingAnalysis?.sections || [],
                },
                analysis: { analysis: '', reasoning: '' },
                revisionNumber: pendingAnalysis?.projectMeta?.revision_number || (selectedProject?.documents?.length || 1),
            };

            setResult(initialResult);

            // Get AI config from localStorage
            const aiConfigStr = localStorage.getItem('aiConfig');
            let aiConfig = { apiUrl: '', apiKey: '', model: '', stream: false };
            if (aiConfigStr) {
                try {
                    aiConfig = JSON.parse(aiConfigStr);
                } catch { }
            }

            // Build previous revisions context for AI comparison
            const allDocs = selectedProject?.documents || [];
            const prevDocs = allDocs
                .filter(d => d.id !== document.id)
                .sort((a, b) => {
                    const revA = parseStoredDocumentAnalysis(a)?.projectMeta?.revision_number || 0;
                    const revB = parseStoredDocumentAnalysis(b)?.projectMeta?.revision_number || 0;
                    return revA - revB;
                });

            const currentRevNum = pendingAnalysis?.projectMeta?.revision_number || (allDocs.length || 1);

            let combinedDocumentContent = document.full_content || '';
            if (prevDocs.length > 0) {
                const prevText = prevDocs.map(d => {
                    const revNum = parseStoredDocumentAnalysis(d)?.projectMeta?.revision_number || 1;
                    return `=== PREVIOUS REVISION (Rev ${revNum}: ${d.filename}) ===\n${d.full_content || ''}`;
                }).join('\n\n');

                combinedDocumentContent = `${prevText}\n\n=== CURRENT REVISION (Rev ${currentRevNum}: ${document.filename}) ===\n${document.full_content || ''}\n\nINSTRUCTIONS FOR REVISION COMPARISON:
Compare CURRENT REVISION (Rev ${currentRevNum}) against PREVIOUS REVISIONS.
Explicitly list what was modified/overridden, what is newly added, and if the product domain has pivoted entirely. Include a dedicated Markdown section titled "## 0.13 Revision Delta & Impact Analysis" with bullet points for:
- **Modified / Overridden Requirements**: List exact items updated from previous revision
- **Newly Added Capabilities**: List exact new items introduced in Rev ${currentRevNum}
- **Scope Divergence / Pivot Evaluation**: State if Rev ${currentRevNum} pivots to a new product domain`;
            }

            if (pendingRepoContext?.context) {
                combinedDocumentContent = `${combinedDocumentContent}\n\n${pendingRepoContext.context}`;
            }

            const aiPayload = {
                document_content: combinedDocumentContent,
                api_url: aiConfig?.apiUrl || undefined,
                api_key: aiConfig?.apiKey || undefined,
                model: aiConfig?.model || undefined,
                stream: aiConfig?.stream || false,
                governance_context: effectiveGovernanceContext || undefined,
            };

            if (aiConfig?.stream || false) {
                await streamAnalysisRef.current(aiPayload, token, initialResult, {
                    repoContext: pendingRepoContext,
                    governanceContext: effectiveGovernanceContext,
                });
            } else {
                setProgress(0);
                setProgressMessage('Submitting analysis request...');
                await fetchAnalysisRef.current(aiPayload, token, initialResult, {
                    repoContext: pendingRepoContext,
                    governanceContext: effectiveGovernanceContext,
                });
            }
        } catch (err) {
            const userFriendlyError = formatAnalysisError(err);
            setError(userFriendlyError || 'Agent Analysis failed.');
        } finally {
            setProcessing(false);
            setAnalysisInProgress(false);
        }
    }, [token, governanceContext, selectedProject, fetchAnalysisRef, streamAnalysisRef, analysisInProgress]);

    useEffect(() => {
        // Don't run if user is on Governance page - analysis should only start from AgentAnalysis page
        const isOnGovernancePage = location.pathname === '/new-project/governance' || location.pathname.startsWith('/new-project/governance');
        if (isOnGovernancePage) {
            setLoading(false);
            return;
        }

        // Don't run if analysis is already in progress
        if (analysisInProgress) {
            console.log('Analysis already in progress, skipping useEffect reload');
            return;
        }

        if (!selectedProjectKey || !selectedProject || projectsLoading) {
            if (!projectsLoading) {
                setLoading(false);
            }
            return;
        }

        // CRITICAL FIX: Check if we're switching to a different project
        const isSwitchingProjects = lastLoadedProjectRef.current && lastLoadedProjectRef.current !== selectedProjectKey;

        // If switching projects, first check if we have cached data for the new project
        if (isSwitchingProjects) {
            if (resultCacheRef.current[selectedProjectKey]) {
                console.log('Restoring cached analysis for project:', selectedProjectKey);
                const cached = resultCacheRef.current[selectedProjectKey];
                setResult(cached.result);
                setAiQuestions(cached.aiQuestions || []);
                setUserAnswers(cached.userAnswers || {});
                setUserFeedback(cached.userFeedback || '');
                setCompletedStages(cached.completedStages || {});
                setChatMessages(cached.chatMessages || []);
                setLoading(false);
                lastLoadedProjectRef.current = selectedProjectKey;
                return;
            } else {
                // Not cached: clear all states to show loading/empty for the new project
                setResult(null);
                setAiQuestions([]);
                setUserAnswers({});
                setUserFeedback('');
                setCompletedStages({});
                setChatMessages([]);
                setError('');
            }
        }

        const loadAnalysis = async () => {
            const latestDoc = selectedProject?.latestDocument;
            const docAlreadyCompleted = hasCompletedDocumentAnalysis(latestDoc);

            if (docAlreadyCompleted) {
                // If the document is already fully analyzed in database, purge any stale job IDs
                localStorage.removeItem('active_analysis_job_id');
                localStorage.removeItem('active_analysis_project_key');
            }

            const storedJobId = localStorage.getItem('active_analysis_job_id');
            const storedProjectKey = localStorage.getItem('active_analysis_project_key');
            if (!docAlreadyCompleted && storedJobId && storedProjectKey === selectedProjectKey) {
                console.log('Found running analysis job in localStorage, resuming polling:', storedJobId);
                const latestDocument = latestDoc;
                const storedAnalysis = parseStoredDocumentAnalysis(latestDocument);
                const initialResult = {
                    id: latestDocument?.id,
                    filename: latestDocument?.filename || 'BRD',
                    extraction: {
                        markdown: latestDocument?.full_content || '',
                        html: '',
                        num_pages: null,
                        sections: storedAnalysis?.sections || [],
                    },
                    analysis: { analysis: '', reasoning: '' },
                    revisionNumber: selectedProject?.documents?.length || 1,
                };
                
                setError('');
                if (latestDocument?.id) {
                    sessionStorage.removeItem(`analysis_error_${latestDocument.id}`);
                }
                resumeAnalysisPollingRef.current(storedJobId, initialResult);
                return;
            }

            setLoading(true);
            setError('');

            try {
                const latestDocument = selectedProject.latestDocument;

                console.log('AgentAnalysis useEffect:', {
                    selectedProjectKey,
                    hasLatestDocument: !!latestDocument,
                    hasRepoContext: !!repoContext,
                    repoContextRepo: repoContext?.repo,
                    repoContextContext: repoContext?.context ? 'present' : 'missing'
                });

                // Check if we have repo context but no document - allow repo-only analysis
                const hasRepoContextOnly = !latestDocument && repoContext?.context;

                console.log('hasRepoContextOnly:', hasRepoContextOnly);

                if (!latestDocument && !hasRepoContextOnly) {
                    setError('No document found for this project. Please upload a document first.');
                    setLoading(false);
                    return;
                }

                // Handle repository-only analysis (no BRD document)
                if (hasRepoContextOnly) {
                    await handleRepositoryOnlyAnalysis();
                    return;
                }

                const storedAnalysis = parseStoredDocumentAnalysis(latestDocument);

                // Check flags first
                const shouldStartAnalysis = sessionStorage.getItem('shouldStartAnalysis') === 'true';
                const analysisStartedKey = `analysis_started_${latestDocument.id}`;
                const alreadyStarted = sessionStorage.getItem(analysisStartedKey) === 'true';

                // Check if analysis is already completed
                if (hasCompletedDocumentAnalysis(latestDocument)) {
                    // Load questions and answers from stored analysis
                    const questions = storedAnalysis?.questions || [];
                    const savedAnswers = storedAnalysis?.userAnswers || {};
                    const savedFeedback = storedAnalysis?.userFeedback || '';
                    const savedStages = storedAnalysis?.stages || {};  // Load saved stages

                    setAiQuestions(questions);
                    setUserAnswers(savedAnswers);
                    setUserFeedback(savedFeedback);
                    setCompletedStages(savedStages);  // Restore completed stages
                    if (storedAnalysis?.hld) {
                        const hld = storedAnalysis.hld;
                        setHldDesign(hld?.markdown ? { ...hld, markdown: sanitizeDesignMarkdownDate(hld.markdown) } : hld);
                    }
                    if (storedAnalysis?.lld) {
                        const lld = storedAnalysis.lld;
                        setLldDesign(lld?.markdown ? { ...lld, markdown: sanitizeDesignMarkdownDate(lld.markdown) } : lld);
                    }
                    if (storedAnalysis?.spec_status) {
                        setSpecStatus(storedAnalysis.spec_status);
                    }

                    const loadedResult = {
                        id: latestDocument.id,
                        filename: latestDocument.filename,
                        _jobId: storedAnalysis?._jobId || null,
                        extraction: {
                            markdown: latestDocument.full_content || '',
                            html: '',
                            num_pages: null,
                            sections: storedAnalysis?.sections || [],
                        },
                        analysis: storedAnalysis,
                        revisionNumber: selectedProject.documents?.length || 1,
                    };

                    setResult(loadedResult);

                    // Load chat messages for this document
                    await loadChatMessages(latestDocument.id);

                    // CRITICAL FIX: Cache the loaded data for this project
                    resultCacheRef.current[selectedProjectKey] = {
                        result: loadedResult,
                        aiQuestions: questions,
                        userAnswers: savedAnswers,
                        userFeedback: savedFeedback,
                        completedStages: savedStages,
                        chatMessages: chatMessages, // Preserve chat history
                    };
                    lastLoadedProjectRef.current = selectedProjectKey;

                    setLoading(false);
                    return;
                }

                // Check if user clicked "Proceed to Agent Analysis" OR if analysis is pending
                const isPending = isPendingGovernanceAnalysis(storedAnalysis);

                if (shouldStartAnalysis || isPending) {
                    // If user clicked "Proceed to Agent Analysis", start the analysis
                    if (shouldStartAnalysis && hasGovernanceAssessment) {
                        // Mark as started to prevent re-triggering
                        sessionStorage.setItem(analysisStartedKey, 'true');
                        // Clear the flag so it doesn't trigger again on refresh
                        sessionStorage.removeItem('shouldStartAnalysis');
                        await triggerPendingAnalysis(latestDocument, storedAnalysis);
                        return;
                    } else if (!hasGovernanceAssessment) {
                        setError('Governance assessment required before analysis.');
                        setLoading(false);
                        return;
                    } else if (alreadyStarted) {
                        // Analysis was started previously
                        // Check if it's currently processing or if it failed
                        if (processing || analysisInProgress) {
                            // Analysis is currently running - don't show error
                            console.log('Analysis is currently running (processing or analysisInProgress)');
                            setLoading(false);
                            return;
                        }

                        // Check if there's an active job in the backend
                        try {
                            const jobIdPattern = /analysis_\d+_\d+_[a-f0-9]+/;
                            const potentialJobId = `analysis_${token ? JSON.parse(atob(token.split('.')[1])).user_id : 'unknown'}_`;

                            // Try to find if there's an active analysis job
                            // We'll check if result exists OR if we should just not show error yet
                            const hasResult = hasCompletedDocumentAnalysis(latestDocument);
 
                            if (!hasResult) {
                                // Guard against race conditions: if component state or project cache already holds
                                // the completed analysis (e.g. while fetchHistory network request is completing),
                                // do NOT show the interrupted error banner!
                                const hasLocalCompletedAnalysis = Boolean(
                                    result?.analysis?.analysis && (result.id === latestDocument?.id || !result.id)
                                );
                                const cachedResult = resultCacheRef.current[selectedProjectKey]?.result;
                                const hasCachedCompletedAnalysis = Boolean(cachedResult?.analysis?.analysis);

                                if (hasLocalCompletedAnalysis || hasCachedCompletedAnalysis) {
                                    setLoading(false);
                                    return;
                                }

                                const activeJobId = localStorage.getItem('active_analysis_job_id');
                                if (!activeJobId) {
                                    const savedErr = sessionStorage.getItem(`analysis_error_${latestDocument.id}`);
                                    setError(savedErr || 'The background analysis job failed or was interrupted. Please check organization permissions and try running the analysis again.');
                                    setLoading(false);
                                    return;
                                }
                                console.log('Analysis was marked as started, but no result yet - might still be initializing');
                                setLoading(false);
                                return;
                            }
                        } catch (err) {
                            console.error('Error checking job status:', err);
                        }

                        return;
                    } else if (isPending) {
                        // Analysis is pending but user hasn't clicked proceed yet
                        setError('Please complete the governance questionnaire and click "Proceed to Agent Analysis" to start the analysis.');
                        setLoading(false);
                        return;
                    }
                }

                const allDocuments = getProcessedProjectDocuments(selectedProject);
                let foundAnalysis = null;
                let foundDoc = null;

                if (selectedDocId) {
                    const match = allDocuments.find(d => d.id === selectedDocId);
                    if (match) {
                        const parsedMatch = parseStoredDocumentAnalysis(match);
                        if (hasCompletedStoredAnalysis(parsedMatch)) {
                            foundDoc = match;
                            foundAnalysis = parsedMatch;
                        }
                    }
                }

                if (!foundDoc) {
                    for (const doc of allDocuments) {
                        const docAnalysis = parseStoredDocumentAnalysis(doc);
                        if (hasCompletedStoredAnalysis(docAnalysis)) {
                            foundAnalysis = docAnalysis;
                            foundDoc = doc;
                            break;
                        }
                    }
                }

                if (foundAnalysis && foundDoc) {
                    // Load questions and answers from stored analysis
                    const questions = foundAnalysis?.questions || [];
                    const savedAnswers = foundAnalysis?.userAnswers || {};
                    const savedFeedback = foundAnalysis?.userFeedback || '';
                    const savedStages = foundAnalysis?.stages || {};  // Load saved stages

                    setAiQuestions(questions);
                    setUserAnswers(savedAnswers);
                    setUserFeedback(savedFeedback);
                    setCompletedStages(savedStages);  // Restore completed stages
                    if (foundAnalysis?.hld) {
                        const hld = foundAnalysis.hld;
                        setHldDesign(hld?.markdown ? { ...hld, markdown: sanitizeDesignMarkdownDate(hld.markdown) } : hld);
                    }
                    if (foundAnalysis?.lld) {
                        const lld = foundAnalysis.lld;
                        setLldDesign(lld?.markdown ? { ...lld, markdown: sanitizeDesignMarkdownDate(lld.markdown) } : lld);
                    }
                    if (foundAnalysis?.spec_status) {
                        setSpecStatus(foundAnalysis.spec_status);
                    }

                    const loadedResult = {
                        id: foundDoc.id,
                        filename: foundDoc.filename,
                        _jobId: foundAnalysis?._jobId || null,
                        extraction: {
                            markdown: foundDoc.full_content || '',
                            html: '',
                            num_pages: null,
                            sections: foundAnalysis?.sections || [],
                        },
                        analysis: foundAnalysis,
                        revisionNumber: selectedProject.documents?.length || 1,
                    };

                    setResult(loadedResult);

                    // CRITICAL FIX: Cache the loaded data for this project
                    resultCacheRef.current[selectedProjectKey] = {
                        result: loadedResult,
                        aiQuestions: questions,
                        userAnswers: savedAnswers,
                        userFeedback: savedFeedback,
                        completedStages: savedStages,
                        chatMessages: chatMessages,
                    };
                    lastLoadedProjectRef.current = selectedProjectKey;
                } else {
                    let hasPendingAnalysis = false;
                    for (const doc of allDocuments) {
                        const docAnalysis = parseStoredDocumentAnalysis(doc);
                        if (isPendingGovernanceAnalysis(docAnalysis)) {
                            hasPendingAnalysis = true;
                            const shouldStartAnalysis = sessionStorage.getItem('shouldStartAnalysis') === 'true';
                            const analysisStartedKey = `analysis_started_${doc.id}`;
                            const alreadyStarted = sessionStorage.getItem(analysisStartedKey) === 'true';

                            // If user clicked "Proceed to Agent Analysis", start the analysis
                            if (shouldStartAnalysis && hasGovernanceAssessment) {
                                sessionStorage.setItem(analysisStartedKey, 'true');
                                sessionStorage.removeItem('shouldStartAnalysis');
                                await triggerPendingAnalysis(doc, docAnalysis);
                                break;
                            } else if (!hasGovernanceAssessment) {
                                setError('Governance assessment required before analysis.');
                                setLoading(false);
                                return;
                            } else if (alreadyStarted) {
                                // Analysis was started previously
                                console.log('Analysis was started but checking status for document', doc.id);

                                // Check if it's currently processing
                                if (processing || analysisInProgress) {
                                    console.log('Analysis is currently running (processing or analysisInProgress)');
                                    setLoading(false);
                                    return;
                                }

                                // Don't immediately show error - analysis might be starting
                                const hasResult = result && result.analysis;
                                if (!hasResult) {
                                    console.log('Analysis was marked as started, but no result yet - might still be initializing');
                                    setLoading(false);
                                    // Don't set error or clear flag - let analysis continue
                                    return;
                                }
                                return;
                            } else {
                                setLoading(false);
                                return;
                            }
                        }
                    }

                    if (!hasPendingAnalysis) {
                        setError('Analysis not yet completed. Please wait for the analysis to finish.');
                    }
                }
            } catch (err) {
                const userFriendlyError = formatAnalysisError(err);
                setError(userFriendlyError || 'Failed to load analysis');
            } finally {
                setLoading(false);
            }
        };

        loadAnalysis();
    }, [selectedProjectKey, selectedProject, projectsLoading, token, hasGovernanceAssessment, location.pathname, analysisInProgress]);
    // Removed: repoContext, triggerPendingAnalysis (to prevent unnecessary re-runs)

    const handleRefineAnalysis = async (overrideFeedback = null, updateType = null) => {
        let feedbackToSend = overrideFeedback || userFeedback;

        // Build Q&A feedback string if questions are present and no override given
        if (!overrideFeedback && aiQuestions.length > 0) {
            feedbackToSend = aiQuestions.map((q, i) => {
                const ans = userAnswers[i] || 'No answer provided';
                return `Q: ${q}\nA: ${ans}`;
            }).join('\n\n');

            if (userFeedback.trim()) {
                feedbackToSend += `\n\nAdditional Comments:\n${userFeedback}`;
            }
        }

        if (!result?.extraction?.markdown || !feedbackToSend.trim()) return;

        setProcessing(true);
        setError('');
        setProgress(20);
        setProgressMessage('Identifying what needs to change...');

        const token = localStorage.getItem('token');
        const aiConfigStr = localStorage.getItem('aiConfig');
        let aiConfig = { apiUrl: '', apiKey: '', model: '', stream: false };
        if (aiConfigStr) {
            try { aiConfig = JSON.parse(aiConfigStr); } catch { }
        }

        // Build the previous_analysis payload for targeted update
        const previousAnalysis = (() => {
            if (!result?.analysis) return undefined;
            const a = result.analysis;
            const stages = a.stages || completedStages || {};
            if (Object.keys(stages).length === 0) return undefined;
            return {
                analysis: a.analysis || '',
                stages,
                metrics: a.metrics || {},
                questions: a.questions || [],
                prerequisites: a.prerequisites || [],
                architecture: a.architecture || {},
            };
        })();

        const detectedUpdateType = updateType
            || (aiQuestions.length > 0 && Object.keys(userAnswers).length > 0 ? 'qa' : 'feedback');

        const aiPayload = {
            document_content: repoContext
                ? `${result.extraction.markdown}\n\n${repoContext.context}`
                : result.extraction.markdown,
            api_url: aiConfig?.apiUrl || undefined,
            api_key: aiConfig?.apiKey || undefined,
            model: aiConfig?.model || undefined,
            stream: false,
            user_feedback: feedbackToSend,
            governance_context: governanceContext || undefined,
            ...(previousAnalysis ? {
                previous_analysis: previousAnalysis,
                update_type: detectedUpdateType,
            } : {}),
        };

        try {
            setProgress(30);
            setProgressMessage('Performing targeted update...');
            const updatedResult = await fetchAnalysisRef.current(aiPayload, token, result, {
                repoContext: repoContext,
                governanceContext: governanceContext,
            });
            return updatedResult;
        } catch (err) {
            const userFriendlyError = formatAnalysisError(err);
            setError(userFriendlyError || 'Failed to update analysis');
            throw err;
        } finally {
            setProcessing(false);
        }
    };

    // ── Fetch Elicitation Techniques ──
    const fetchElicitationTechniques = useCallback(async (projectToken, onlySkills = false) => {
        if (!projectToken || !token) return;
        setTechniquesLoading(true);
        setTechniquesError('');
        try {
            const url = `${API_ENDPOINTS.GOVERNANCE_ELICITATION_TECHNIQUES(projectToken)}${onlySkills ? '?only_skills=true' : ''}`;
            const response = await fetch(url, {
                headers: {
                    'Authorization': `Bearer ${token}`,
                },
            });
            if (response.ok) {
                const data = await response.json();
                setElicitationTechniques(data.techniques || []);
                setTechniquesSource(data.source || 'ai_generated');
            } else {
                console.error('Failed to fetch elicitation techniques:', await response.text());
                setTechniquesError('Failed to load requirement elicitation techniques.');
            }
        } catch (err) {
            console.error('Error fetching elicitation techniques:', err);
            setTechniquesError('Error connecting to techniques engine.');
            setElicitationTechniques([]);
        } finally {
            setTechniquesLoading(false);
        }
    }, [token]);

    // Fetch techniques when project switches (only check for pre-uploaded skills files on load)
    useEffect(() => {
        if (selectedProjectKey) {
            fetchElicitationTechniques(selectedProjectKey, true);
        }
    }, [selectedProjectKey, fetchElicitationTechniques]);

    // ── Load chat messages from database ──
    const loadChatMessages = useCallback(async (documentId) => {
        if (!documentId || !token) return;

        try {
            const response = await fetch(API_ENDPOINTS.CHAT_MESSAGES_GET(documentId), {
                headers: {
                    'Authorization': `Bearer ${token}`,
                },
            });

            if (response.ok) {
                const messages = await response.json();
                setChatMessages(messages);
                console.log(`Loaded ${messages.length} chat messages for document ${documentId}`);
            }
        } catch (err) {
            console.error('Failed to load chat messages:', err);
        }
    }, [token]);

    // ── Save chat message to database ──
    const saveChatMessage = useCallback(async (message) => {
        if (!result?.id || !token) return;

        try {
            const response = await fetch(API_ENDPOINTS.CHAT_MESSAGES_SAVE, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({
                    document_id: result.id,
                    role: message.role,
                    content: message.content,
                    is_error: message.isError || false,
                    is_qa: message.isQA || false,
                    affected_sections: message.affectedSections || null,
                    change_summary: message.changeSummary || null,
                }),
            });

            if (!response.ok) {
                console.error('Failed to save chat message:', await response.text());
            }
        } catch (err) {
            console.error('Error saving chat message:', err);
        }
    }, [result, token]);

    // ── Apply planned changes from discussion to BRD ──
    const handleApplyDiscussionToBRD = async () => {
        setDiscussMode(false);
        const feedbackText = (() => {
            const historyContext = chatMessages
                .filter(m => m.id !== 'welcome-elicitation')
                .map(m => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`)
                .join('\n\n');
            return `Please update the BRD based on the following conversation:\n\n${historyContext}\n\nApply the discussed changes.`;
        })();

        const msgId = `msg_${Date.now()}`;
        const userMsg = {
            id: msgId,
            role: 'user',
            content: "Apply discussion to update BRD",
            timestamp: new Date().toISOString(),
        };

        setChatMessages(prev => [...prev, userMsg]);
        setChatSending(true);
        await saveChatMessage(userMsg);

        try {
            const updatedResult = await handleRefineAnalysis(feedbackText, 'feedback');

            const assistantMsg = {
                id: `resp_${Date.now()}`,
                role: 'assistant',
                content: updatedResult?.analysis?.change_summary
                    || 'Analysis updated successfully based on your input.',
                affectedSections: updatedResult?.analysis?.affected_sections || [],
                changeSummary: updatedResult?.analysis?.change_summary,
                timestamp: new Date().toISOString(),
            };
            setChatMessages(prev => [...prev, assistantMsg]);
            await saveChatMessage(assistantMsg);
        } catch (err) {
            const friendlyErr = formatAnalysisError(err);
            const errMsg = {
                id: `err_${Date.now()}`,
                role: 'assistant',
                content: friendlyErr,
                isError: true,
                timestamp: new Date().toISOString(),
            };
            setChatMessages(prev => [...prev, errMsg]);
            await saveChatMessage(errMsg);
        } finally {
            setChatSending(false);
        }
    };

    // ── Predefined Suggested Options click handler ──
    const handleSuggestedOption = async (option) => {
        if (chatSending || processing) return;

        if (option === 'generate_techniques') {
            setDiscussMode(true);
            const userMsg = {
                id: `msg_${Date.now()}`,
                role: 'user',
                content: "Please generate requirements elicitation techniques for this project.",
                timestamp: new Date().toISOString(),
            };
            setChatMessages(prev => [...prev, userMsg]);
            setChatSending(true);
            await saveChatMessage(userMsg);

            try {
                // Call techniques API (force only_skills=false for AI generation)
                await fetchElicitationTechniques(selectedProjectKey, false);
                
                const assistantMsg = {
                    id: `resp_${Date.now()}`,
                    role: 'assistant',
                    content: "I have completed the analysis and generated 5 tailored elicitation techniques based on the AI report. Select any technique below to surgically enhance your BRD.",
                    timestamp: new Date().toISOString(),
                };
                setChatMessages(prev => [...prev, assistantMsg]);
                await saveChatMessage(assistantMsg);
            } catch (err) {
                const friendlyErr = formatAnalysisError(err);
                const errMsg = {
                    id: `err_${Date.now()}`,
                    role: 'assistant',
                    content: friendlyErr,
                    isError: true,
                    timestamp: new Date().toISOString(),
                };
                setChatMessages(prev => [...prev, errMsg]);
                await saveChatMessage(errMsg);
            } finally {
                setChatSending(false);
            }
        } else if (option === 'identify_gaps') {
            setDiscussMode(true);
            setChatInput("Can you analyze this BRD and identify potential edge cases, logic gaps, or missing requirements?");
        } else if (option === 'summarize_report') {
            setDiscussMode(true);
            setChatInput("Please summarize the key findings, complexity metrics, and next steps from the generated Action Plan.");
        }
    };

    // ── Chat-based BRD update handler ──
    const handleChatSend = async () => {
        const message = chatInput.trim();
        if (!message || chatSending || processing) return;

        const msgId = `msg_${Date.now()}`;
        const userMsg = {
            id: msgId,
            role: 'user',
            content: message,
            timestamp: new Date().toISOString(),
        };

        setChatMessages(prev => [...prev, userMsg]);
        setChatInput('');
        setChatSending(true);

        // Save user message to database
        await saveChatMessage(userMsg);

        try {
            if (!discussMode) {
                // Direct BRD Update mode (discussMode is false)
                const updatedResult = await handleRefineAnalysis(message, 'feedback');

                // After analysis completes, add an assistant confirmation message
                const assistantMsg = {
                    id: `resp_${Date.now()}`,
                    role: 'assistant',
                    content: updatedResult?.analysis?.change_summary
                        || 'Analysis updated successfully based on your input.',
                    affectedSections: updatedResult?.analysis?.affected_sections || [],
                    changeSummary: updatedResult?.analysis?.change_summary,
                    timestamp: new Date().toISOString(),
                };
                setChatMessages(prev => [...prev, assistantMsg]);

                // Save assistant message to database
                await saveChatMessage(assistantMsg);
            } else {
                // Discuss mode: call conversational chat API
                const response = await fetch(`${API_BASE_URL}/api/agent/brd-chat`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({
                        project_token: selectedProjectKey,
                        message: message,
                        conversation_history: chatMessages
                            .filter(m => m.id !== 'welcome-elicitation')
                            .map(m => ({ role: m.role, content: m.content }))
                    })
                });

                if (!response.ok) {
                    throw new Error(await response.text());
                }

                const data = await response.json();
                const assistantMsg = {
                    id: `resp_${Date.now()}`,
                    role: 'assistant',
                    content: data.response,
                    timestamp: new Date().toISOString(),
                };
                setChatMessages(prev => [...prev, assistantMsg]);
                await saveChatMessage(assistantMsg);
            }
        } catch (err) {
            const friendlyErr = formatAnalysisError(err);
            const errMsg = {
                id: `err_${Date.now()}`,
                role: 'assistant',
                content: friendlyErr,
                isError: true,
                timestamp: new Date().toISOString(),
            };
            setChatMessages(prev => [...prev, errMsg]);

            // Save error message to database
            await saveChatMessage(errMsg);
        } finally {
            setChatSending(false);
            // Scroll to bottom of chat
            setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
        }
    };

    // ── Apply elicitation technique ──
    const handleApplyTechnique = async (tech) => {
        if (chatSending || processing) return;

        const promptText = `Please apply the "${tech.name}" elicitation technique to surgically enhance and discover edge-case requirements for this BRD.\n\nMethodology Instructions:\n"${tech.description}"`;

        const msgId = `msg_${Date.now()}`;
        const userMsg = {
            id: msgId,
            role: 'user',
            content: `**Applying requirements elicitation technique: [${tech.name}]**\n\n*Using methodology instructions:* \n> ${tech.description.replace(/\n/g, ' ')}\n\nProcessing BRD enhancement based on this SDLC process.`,
            timestamp: new Date().toISOString(),
        };

        setChatMessages(prev => [...prev, userMsg]);
        setChatSending(true);

        // Save user message to database
        await saveChatMessage(userMsg);

        try {
            const updated = await handleRefineAnalysis(promptText, 'feedback');

            // Add the assistant confirmation message with the ACTUAL change_summary!
            const assistantMsg = {
                id: `resp_${Date.now()}`,
                role: 'assistant',
                content: updated?.analysis?.change_summary
                    || `BRD successfully enhanced and updated based on the [${tech.name}] elicitation technique.`,
                affectedSections: updated?.analysis?.affected_sections || [],
                changeSummary: updated?.analysis?.change_summary,
                timestamp: new Date().toISOString(),
            };
            setChatMessages(prev => [...prev, assistantMsg]);
            await saveChatMessage(assistantMsg);
        } catch (err) {
            const friendlyErr = formatAnalysisError(err);
            const errMsg = {
                id: `err_${Date.now()}`,
                role: 'assistant',
                content: friendlyErr,
                isError: true,
                timestamp: new Date().toISOString(),
            };
            setChatMessages(prev => [...prev, errMsg]);
            await saveChatMessage(errMsg);
        } finally {
            setChatSending(false);
            setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
        }
    };

    // ── Handle Q&A submission as chat ──
    const handleQASubmit = async () => {
        const questions = aiQuestions?.length > 0 ? aiQuestions : (result?.analysis?.questions || []);
        if (questions.length === 0) return;

        const qaPairs = questions.map((q, i) => {
            const ans = userAnswers[i] || 'No answer provided';
            return `Q: ${q}\nA: ${ans}`;
        }).join('\n\n');

        if (!qaPairs.trim()) return;

        const userMsg = {
            id: `qa_${Date.now()}`,
            role: 'user',
            content: `**Answering clarification questions:**\n\n${qaPairs}`,
            timestamp: new Date().toISOString(),
            isQA: true,
        };

        setChatMessages(prev => [...prev, userMsg]);
        setChatSending(true);

        // Save user message to database
        await saveChatMessage(userMsg);

        try {
            await handleRefineAnalysis(qaPairs, 'qa');
            setUserAnswers({});

            const assistantMsg = {
                id: `qa_resp_${Date.now()}`,
                role: 'assistant',
                content: result?.analysis?.change_summary
                    || 'Analysis updated based on your answers.',
                affectedSections: result?.analysis?.affected_sections || [],
                changeSummary: result?.analysis?.change_summary,
                timestamp: new Date().toISOString(),
            };
            setChatMessages(prev => [...prev, assistantMsg]);

            // Save assistant message to database
            await saveChatMessage(assistantMsg);
        } catch (err) {
            const friendlyErr = formatAnalysisError(err);
            const errMsg = {
                id: `qa_err_${Date.now()}`,
                role: 'assistant',
                content: friendlyErr,
                isError: true,
                timestamp: new Date().toISOString(),
            };
            setChatMessages(prev => [...prev, errMsg]);

            // Save error message to database
            await saveChatMessage(errMsg);
        } finally {
            setChatSending(false);
            setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
        }
    };

    // ── Memoized Chat Messages with Prepend Welcome Elicitation Message ──
    const renderedMessages = useMemo(() => {
        if (elicitationTechniques.length === 0) return chatMessages;

        // Check if welcome message is already in chatMessages from DB to avoid duplicating it
        const hasWelcome = chatMessages.some(m => m.id === 'welcome-elicitation');
        if (hasWelcome) return chatMessages;

        const welcomeMsg = {
            id: 'welcome-elicitation',
            role: 'assistant',
            content: `Hello! I have completed the initial BRD analysis. Below are 5 tailored requirements elicitation techniques synthesized based on the project requirements. Select any technique below to surgically enhance your BRD:`,
            timestamp: result?.upload_date || new Date().toISOString(),
            isElicitation: true
        };

        return [welcomeMsg, ...chatMessages];
    }, [chatMessages, elicitationTechniques, result]);

    // ── Memoized custom Markdown components to prevent unmounting/remounting on parent state change ──
    const markdownComponents = useMemo(() => ({
        h1: ({ node, ...props }) => <h1 className="text-lg font-bold text-gray-900 mt-6 mb-3 pb-2 border-b-2 border-gray-200" {...props} />,
        h2: ({ node, children, ...props }) => {
            const extractText = (elem) => {
                if (!elem) return '';
                if (typeof elem === 'string') return elem;
                if (Array.isArray(elem)) return elem.map(extractText).join('');
                if (elem?.props?.children) return extractText(elem.props.children);
                return String(elem || '');
            };
            const headingText = extractText(children);
            const isDatabaseDesign = /database detailed design/i.test(headingText);

            if (isDatabaseDesign) {
                return (
                    <div className="flex flex-wrap items-center justify-between gap-3 mt-6 mb-3 pb-2 border-b-2 border-gray-200">
                        <h2 className="text-base font-bold text-gray-900 m-0 border-b-0" {...props}>
                            {children}
                        </h2>
                        <button
                            onClick={handleCopyDdl}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-all shadow-sm flex-shrink-0"
                            title="Copy SQL Migration DDL"
                        >
                            {copiedSnippet === 'ddl' ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                            <span>{copiedSnippet === 'ddl' ? 'DDL Copied!' : 'Copy DDL'}</span>
                        </button>
                    </div>
                );
            }

            return <h2 className="text-base font-bold text-gray-900 mt-5 mb-2 pb-1 border-b border-gray-200" {...props}>{children}</h2>;
        },
        h3: ({ node, ...props }) => <h3 className="text-sm font-semibold text-gray-800 mt-4 mb-2" {...props} />,
        h4: ({ node, ...props }) => <h4 className="text-sm font-semibold text-gray-700 mt-3 mb-1" {...props} />,
        p: ({ node, ...props }) => <p className="text-sm text-gray-700 leading-relaxed mb-3" {...props} />,
        ul: ({ node, ...props }) => <ul className="list-disc list-outside ml-5 space-y-1 mb-3 text-sm text-gray-700" {...props} />,
        ol: ({ node, ...props }) => <ol className="list-decimal list-outside ml-5 space-y-1 mb-3 text-sm text-gray-700" {...props} />,
        li: ({ node, ...props }) => <li className="leading-relaxed text-sm" {...props} />,
        table: ({ node, ...props }) => (
            <div className="overflow-x-auto my-3 w-full border border-gray-200 rounded-lg max-w-full shadow-xs">
                <table className="w-full divide-y divide-gray-200 table-auto text-xs" {...props} />
            </div>
        ),
        thead: ({ node, ...props }) => <thead className="bg-gray-50/80" {...props} />,
        tbody: ({ node, ...props }) => <tbody className="divide-y divide-gray-100 bg-white" {...props} />,
        tr: ({ node, ...props }) => <tr className="hover:bg-gray-50/40 transition-colors" {...props} />,
        th: ({ node, ...props }) => <th className="px-3 py-1.5 text-left font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200 whitespace-normal leading-tight text-[11px]" {...props} />,
        td: ({ node, ...props }) => <td className="px-3 py-1.5 text-gray-700 border-t border-gray-100 whitespace-normal leading-snug align-top text-xs" {...props} />,
        code: ({ node, inline, className, children, ...props }) => {
            const extractText = (elem) => {
                if (!elem) return '';
                if (typeof elem === 'string') return elem;
                if (Array.isArray(elem)) return elem.map(extractText).join('');
                if (elem?.props?.children) return extractText(elem.props.children);
                return String(elem || '');
            };
            const codeContent = extractText(children).trim();
            const lang = (className || '').toLowerCase();

            const isInline = inline === true || (
                inline === undefined &&
                !lang &&
                !codeContent.includes('\n') &&
                (!node?.position || node.position.start.line === node.position.end.line)
            );

            if (isInline) {
                return (
                    <code
                        className="inline-block bg-slate-100 text-slate-800 font-mono text-[11px] font-semibold px-1.5 py-0.5 rounded border border-slate-200/80 mx-0.5 my-0.5 leading-tight"
                        {...props}
                    >
                        {children}
                    </code>
                );
            }

            const isMermaid = lang.includes('mermaid') ||
                codeContent.startsWith('graph') ||
                codeContent.includes('flowchart') ||
                codeContent.includes('sequenceDiagram') ||
                codeContent.includes('classDiagram') ||
                codeContent.includes('stateDiagram') ||
                codeContent.includes('stateDiagram-v2') ||
                codeContent.includes('erDiagram') ||
                codeContent.toLowerCase().includes('erdiagram') ||
                codeContent.includes('||--') ||
                codeContent.includes('}o--') ||
                codeContent.includes('|o--');

            if (isMermaid) {
                return <MermaidDiagram code={codeContent} showDownload={true} />;
            }

            const isSql = lang.includes('sql') ||
                codeContent.toLowerCase().includes('create table') ||
                codeContent.toLowerCase().includes('create extension') ||
                codeContent.toLowerCase().includes('create or replace function') ||
                codeContent.toLowerCase().includes('-- database schema') ||
                codeContent.toLowerCase().includes('migration ddl');

            if (isSql) {
                return (
                    <div className="my-4 rounded-xl border border-gray-800 bg-gray-900 overflow-hidden shadow-sm">
                        <div className="flex items-center justify-between px-4 py-2 bg-gray-800/90 border-b border-gray-700">
                            <span className="text-[11px] font-mono font-semibold text-gray-300 uppercase tracking-wider">
                                SQL Migration DDL
                            </span>
                            <button
                                onClick={() => {
                                    navigator.clipboard.writeText(codeContent);
                                    setCopiedSnippet('ddl');
                                    setTimeout(() => setCopiedSnippet(null), 2500);
                                }}
                                className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold text-gray-200 bg-gray-700 hover:bg-gray-600 rounded-md transition-all shadow-xs"
                                title="Copy SQL Migration DDL"
                            >
                                {copiedSnippet === 'ddl' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-gray-300" />}
                                <span>{copiedSnippet === 'ddl' ? 'DDL Copied!' : 'Copy DDL'}</span>
                            </button>
                        </div>
                        <pre className="p-4 text-gray-100 text-xs font-mono overflow-x-auto whitespace-pre leading-relaxed">
                            <code className="text-gray-100 font-mono whitespace-pre" {...props}>{children}</code>
                        </pre>
                    </div>
                );
            }

            return (
                <div className="my-4 rounded-xl border border-gray-800 bg-gray-900 overflow-hidden shadow-sm">
                    <pre className="p-4 text-gray-100 text-xs font-mono overflow-x-auto whitespace-pre leading-relaxed">
                        <code className="text-gray-100 font-mono whitespace-pre" {...props}>{children}</code>
                    </pre>
                </div>
            );
        },
        pre: ({ node, children, ...props }) => {
            return <>{children}</>;
        },
        blockquote: ({ node, ...props }) => <blockquote className="border-l-4 border-blue-500 pl-4 italic text-gray-600 my-4 bg-blue-50 py-2" {...props} />,
        a: ({ node, ...props }) => <a className="text-blue-600 hover:text-blue-800 underline font-medium" {...props} />,
        strong: ({ node, ...props }) => <strong className="font-bold text-gray-900" {...props} />,
    }), [handleCopyDdl, copiedSnippet]);

    // ── Helper: render a mermaid code string to a PNG data-URL ──
    const renderMermaidToPng = async (mermaidCode) => {
        try {
            const sanitized = sanitizeMermaidCode(mermaidCode);
            const uniqueId = `pdf-mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
            const { svg } = await safeRenderMermaid(uniqueId, sanitized);

            return await new Promise((resolve) => {
                // Parse SVG and force high-resolution dimensions before rasterizing
                const parser = new DOMParser();
                const svgDoc = parser.parseFromString(svg, 'image/svg+xml');
                const svgEl = svgDoc.querySelector('svg');

                let targetW = 2400; // Crisp 300+ DPI target width for razor-sharp typography
                let aspectRatio = 0.55; // default fallback

                if (svgEl) {
                    // Read viewBox to get intrinsic aspect ratio
                    const vb = svgEl.getAttribute('viewBox');
                    if (vb) {
                        const parts = vb.trim().split(/[\s,]+/);
                        if (parts.length === 4) {
                            const vbW = parseFloat(parts[2]);
                            const vbH = parseFloat(parts[3]);
                            if (vbW > 0 && vbH > 0) {
                                aspectRatio = Math.min(vbH / vbW, 2.8);
                            }
                        }
                    } else {
                        // Fallback: read explicit width/height attrs
                        const attrW = parseFloat(svgEl.getAttribute('width') || '0');
                        const attrH = parseFloat(svgEl.getAttribute('height') || '0');
                        if (attrW > 0 && attrH > 0) {
                            aspectRatio = Math.min(attrH / attrW, 2.8);
                        }
                    }
                    // Force explicit pixel dimensions so the browser renders at full high resolution
                    const targetH = Math.round(targetW * aspectRatio);
                    svgEl.setAttribute('width', String(targetW));
                    svgEl.setAttribute('height', String(targetH));

                    // Inject crisp typography styles into SVG to ensure clear, high-contrast, non-blurry text
                    const styleEl = svgDoc.createElementNS('http://www.w3.org/2000/svg', 'style');
                    styleEl.textContent = `
                        text, tspan, .nodeLabel, .actor, .messageText, .labelText, .label, .edgeLabel {
                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
                            text-rendering: geometricPrecision !important;
                            -webkit-font-smoothing: antialiased !important;
                            font-weight: 500 !important;
                        }
                        .node .label, .actor, .cluster-label, text.actor {
                            font-weight: 700 !important;
                        }
                    `;
                    svgEl.prepend(styleEl);
                }

                const targetH = Math.round(targetW * aspectRatio);
                const modifiedSvg = new XMLSerializer().serializeToString(svgDoc);
                const svgBlob = new Blob([modifiedSvg], { type: 'image/svg+xml;charset=utf-8' });
                const reader = new FileReader();

                reader.onload = () => {
                    const img = new Image();
                    const dataUrl = reader.result;

                    img.onload = () => {
                        try {
                            // Direct 1:1 canvas mapping at 2400px target resolution
                            const canvasW = targetW;
                            const canvasH = targetH;

                            const canvas = document.createElement('canvas');
                            canvas.width = canvasW;
                            canvas.height = canvasH;

                            const ctx = canvas.getContext('2d');
                            if (!ctx) { resolve(null); return; }

                            // Solid white background for clean contrast & compatibility
                            ctx.fillStyle = '#ffffff';
                            ctx.fillRect(0, 0, canvasW, canvasH);

                            ctx.imageSmoothingEnabled = true;
                            ctx.imageSmoothingQuality = 'high';
                            ctx.drawImage(img, 0, 0, canvasW, canvasH);

                            // Lossless PNG: zero compression artifacts, razor-sharp text, ~25KB compressed size
                            const pngDataUrl = canvas.toDataURL('image/png');
                            resolve({ dataUrl: pngDataUrl, aspectRatio });
                        } catch (drawError) {
                            console.warn('Canvas draw error:', drawError);
                            resolve(null);
                        }
                    };

                    img.onerror = () => { console.warn('Image load error'); resolve(null); };
                    img.src = dataUrl;
                };

                reader.onerror = () => { console.warn('FileReader error'); resolve(null); };
                reader.readAsDataURL(svgBlob);
            });
        } catch (err) {
            console.warn('Mermaid→PNG render failed:', err);
            return null;
        }
    };

    // ── Helper: replace Unicode / box-drawing tree chars with ASCII equivalents ──
    const normalizeTreeChars = (text) =>
        text
            .replace(/├──/g, '+--')
            .replace(/└──/g, '\\--')
            .replace(/│/g, '|')
            .replace(/─/g, '-')
            .replace(/├/g, '+')
            .replace(/└/g, '\\')
            .replace(/┌/g, '+')
            .replace(/┐/g, '+')
            .replace(/┘/g, '+')
            .replace(/┼/g, '+')
            .replace(/┤/g, '+')
            // Handle the %%% / %ˇ style chars produced by some AI outputs
            .replace(/%+\s*%+\s*%+\s*/g, '+-- ')
            .replace(/%+\s+%+\s*%+\s*/g, '|   +-- ')
            .replace(/^%+\s*/gm, '|   ');

    const handleDownloadPDF = async () => {
        if (!result?.analysis) return;

        const { jsPDF } = await import('jspdf');
        const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4', compress: true });
        const pageWidth = doc.internal.pageSize.getWidth();
        const pageHeight = doc.internal.pageSize.getHeight();
        const marginLeft = 20;
        const marginRight = 20;

        // Load logo as base64 for embedding in PDF
        let logoBase64 = null;
        try {
            const logoResponse = await fetch(bourntecLogo);
            const logoBlob = await logoResponse.blob();
            logoBase64 = await new Promise((resolve) => {
                const reader = new FileReader();
                reader.onloadend = () => resolve(reader.result);
                reader.readAsDataURL(logoBlob);
            });
        } catch (e) {
            console.warn('Could not load logo for PDF', e);
        }
        const contentWidth = pageWidth - marginLeft - marginRight;
        let y = 0;

        // ── Colors ──
        const brandBlue = [30, 58, 138];       // deep indigo
        const brandAccent = [59, 130, 246];     // blue-500
        const darkText = [31, 41, 55];          // gray-800
        const mutedText = [107, 114, 128];      // gray-500
        const lightBg = [248, 250, 252];        // slate-50
        const white = [255, 255, 255];

        // ── Clean text for PDF helper to prevent characters spacing corruption ──
        const cleanTextForPdf = (text) => {
            if (!text) return '';
            return String(text)
                .replace(/[\u200b\u200c\u200d\ufeff]/g, '')
                .replace(/[\u2011\u2013\u2014\u2015]/g, '-')
                .replace(/\u00a0/g, ' ')
                .replace(/\u00ad/g, '')
                .replace(/[\u2018\u2019]/g, "'")
                .replace(/[\u201C\u201D]/g, '"')
                .replace(/\u2026/g, '...')
                .replace(/[\u2022\u2023\u2043\u25E6\u25AA\u25AB•]/g, '-')
                .replace(/\u2264/g, '<=')
                .replace(/\u2265/g, '>=')
                .replace(/[^\x00-\x7F]/g, (match) => {
                    const charCode = match.charCodeAt(0);
                    if (charCode >= 192 && charCode <= 255) {
                        return match;
                    }
                    return ' ';
                });
        };

        // ── Helper: add page footer ──
        const addFooter = (pageNum, totalPagesCount) => {
            doc.setDrawColor(...brandBlue);
            doc.setLineWidth(0.3);
            doc.line(marginLeft, pageHeight - 15, pageWidth - marginRight, pageHeight - 15);
            doc.setFontSize(7);
            doc.setTextColor(...mutedText);
            doc.setFont('helvetica', 'normal');
            doc.text('Confidential — DSuite by Bourntec Solutions', marginLeft, pageHeight - 10);
            doc.text(`Page ${pageNum} of ${totalPagesCount}`, pageWidth - marginRight, pageHeight - 10, { align: 'right' });
            doc.text(new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }), pageWidth / 2, pageHeight - 10, { align: 'center' });
        };

        const checkPage = (needed = 12) => {
            if (y + needed > pageHeight - 22) {
                doc.addPage();
                y = 20;
            }
        };

        // ══════════════════════════════════════════
        //  PAGE 1: COVER / HEADER
        // ══════════════════════════════════════════

        // Top brand bar
        doc.setFillColor(...brandBlue);
        doc.rect(0, 0, pageWidth, 52, 'F');

        // Bourntec logo + DSuite branding (right side of header)
        // Bourntec logo + DSuite branding (top right corner)
        // if (logoBase64) {
        //     try {
        //         doc.addImage(logoBase64, 'PNG', pageWidth - marginRight - 48, 6, 44, 13);
        //     } catch (e) {
        //         console.warn('Logo embed failed', e);
        //     }
        // }

        // // Vertical divider line (like the sidebar separator)
        // doc.setDrawColor(200, 210, 230);
        // doc.setLineWidth(0.4);
        // doc.line(pageWidth - marginRight - 48, 22, pageWidth - marginRight - 48, 29);

        // // "Powered by" immediately left of divider
        // doc.setTextColor(200, 210, 230);
        // doc.setFontSize(7);
        // doc.setFont('helvetica', 'normal');
        // doc.text('Powered by', pageWidth - marginRight - 46, 27);

        // // "DSuite" immediately right of divider — tight gap
        // doc.setTextColor(255, 255, 255);
        // doc.setFontSize(7);
        // doc.setFont('helvetica', 'bold');
        // doc.text('DSuite', pageWidth - marginRight - 18, 27);

        if (logoBase64) {
            try {
                // Wider width to prevent squishing — maintain natural aspect ratio
                doc.addImage(logoBase64, 'PNG', pageWidth - marginRight - 62, 8, 44, 10);
            } catch (e) {
                console.warn('Logo embed failed', e);
            }
        }

        // Vertical divider — shift right to match wider logo
        doc.setDrawColor(180, 190, 210);
        doc.setLineWidth(0.5);
        doc.line(pageWidth - marginRight - 14, 7, pageWidth - marginRight - 14, 19);

        // DSuite text — stays same position
        doc.setTextColor(255, 255, 255);
        doc.setFontSize(9);
        doc.setFont('helvetica', 'bold');
        doc.text('DSuite', pageWidth - marginRight - 11, 15);

        // Title block (left side)
        doc.setTextColor(...white);
        doc.setFontSize(22);
        doc.setFont('helvetica', 'bold');
        doc.text('BRD Analysis Report', marginLeft, 20);

        doc.setFontSize(10);
        doc.setFont('helvetica', 'normal');
        const projectLabel = cleanTextForPdf(selectedProject?.name || result.filename || 'Project Analysis');
        doc.text(projectLabel, marginLeft, 31);

        doc.setFontSize(8);
        doc.setTextColor(200, 210, 230);
        doc.text(`Generated: ${new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}`, marginLeft, 41);
        doc.text(`${selectedProject?.name ? cleanTextForPdf(selectedProject.name) + ' • ' : ''}Confidential`, marginLeft, 48);

        y = 62;

        // ── Key Metrics Cards ──
        const metrics = result.analysis.metrics || {};
        const metricItems = [
            { label: 'Deployment', value: metrics.deployment || 'TBD' },
            { label: 'Resources', value: metrics.resources || 'TBD' },
            { label: 'Complexity', value: metrics.complexity || 'TBD' },
            { label: 'Timeline (For Developer Only Mode)', value: metrics.timeline || 'TBD' },
        ];

        const cardW = (contentWidth - 9) / 4;
        const cardH = 22;

        metricItems.forEach((m, i) => {
            const x = marginLeft + i * (cardW + 3);
            // Card bg
            doc.setFillColor(...lightBg);
            doc.roundedRect(x, y, cardW, cardH, 2, 2, 'F');
            // Left accent bar
            doc.setFillColor(...brandAccent);
            doc.rect(x, y, 1.5, cardH, 'F');
            // Label
            doc.setFontSize(7);
            doc.setFont('helvetica', 'normal');
            doc.setTextColor(...mutedText);
            doc.text(m.label.toUpperCase(), x + 5, y + 7);
            // Value
            doc.setFontSize(9);
            doc.setFont('helvetica', 'bold');
            doc.setTextColor(...darkText);
            const valLines = doc.splitTextToSize(cleanTextForPdf(String(m.value)), cardW - 8);
            doc.text(valLines.slice(0, 2), x + 5, y + 14);
        });

        y += cardH + 10;

        // ── Separator ──
        doc.setDrawColor(220, 220, 230);
        doc.setLineWidth(0.2);
        doc.line(marginLeft, y, pageWidth - marginRight, y);
        y += 8;

        // ══════════════════════════════════════════
        //  ANALYSIS CONTENT
        // ══════════════════════════════════════════
        const analysisContent = result.analysis?.analysis || '';

        // Strip HTML tags for plain text if content is HTML
        const stripHtml = (html) => {
            if (!html) return '';
            return html
                .replace(/<br\s*\/?>/gi, '\n')
                .replace(/<\/(?:li|p|div|tr|h\d)>/gi, '\n')
                .replace(/<li[^>]*>/gi, '• ')
                .replace(/<[^>]*>/g, '')
                .replace(/&amp;/g, '&')
                .replace(/&lt;/g, '<')
                .replace(/&gt;/g, '>')
                .replace(/&quot;/g, '"')
                .replace(/&#39;/g, "'")
                .replace(/\n{3,}/g, '\n\n')
                .trim();
        };

        const rawTextRaw = isLikelyHtml(analysisContent) ? stripHtml(analysisContent) : analysisContent;
        const rawText = cleanTextForPdf(rawTextRaw);
        const lines = rawText.split('\n');

        // ── Pre-render every mermaid block to PNG so we can embed them ──
        const mermaidImages = [];
        const erDiagramImages = [];
        {
            const mermaidRegex = /```mermaid\s*([\s\S]*?)```/g;
            let mMatch;
            while ((mMatch = mermaidRegex.exec(rawText)) !== null) {
                const code = mMatch[1].trim();
                // eslint-disable-next-line no-await-in-loop
                const imgData = await renderMermaidToPng(code);
                mermaidImages.push(imgData); // may be null if render failed
            }
        }
        // Also pre-render erDiagram blocks
        {
            const erRegex = /```(?:erDiagram|erdiagram)([\s\S]*?)```/gi;
            let erMatch;
            while ((erMatch = erRegex.exec(rawText)) !== null) {
                const code = erMatch[1].trim();
                // eslint-disable-next-line no-await-in-loop
                const imgData = await renderMermaidToPng(code);
                erDiagramImages.push(imgData);
            }
        }
        let mermaidImageIdx = 0;
        let erDiagramImageIdx = 0;

        // Section title
        doc.setFontSize(14);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(...brandBlue);
        doc.text('Executive Summary & Agent Analysis', marginLeft, y);
        y += 8;

        let inCodeBlock = false;
        let codeBlockType = '';
        let codeBlockContent = [];
        let skipFolderStructure = false;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const trimmed = line.trim();

            // ── Detect code block start ──
            if (trimmed.startsWith('```')) {
                if (!inCodeBlock) {
                    inCodeBlock = true;
                    codeBlockType = trimmed.substring(3).trim();
                    codeBlockContent = [];
                    continue;
                } else {
                    // Code block end
                    inCodeBlock = false;

                    // Handle different code block types
                    if (codeBlockType === 'mermaid') {
                        // ── Embed actual rendered PNG image ──
                        const imgData = mermaidImages[mermaidImageIdx++] || null;
                        if (imgData && imgData.dataUrl) {
                            let imgW = contentWidth;
                            const maxHeight = pageHeight - 65; // Leave room for running header & footer
                            let imgH = imgW * (imgData.aspectRatio || 0.55);
                            // If image is taller than page, scale both width & height to preserve true aspect ratio
                            if (imgH > maxHeight) {
                                imgH = maxHeight;
                                imgW = imgH / (imgData.aspectRatio || 0.55);
                            }
                            checkPage(imgH + 10);
                            // light background card
                            doc.setFillColor(...lightBg);
                            doc.roundedRect(marginLeft, y, contentWidth, imgH + 6, 2, 2, 'F');
                            doc.setFillColor(...brandAccent);
                            doc.rect(marginLeft, y, 2, imgH + 6, 'F');
                            const offsetX = marginLeft + (contentWidth - imgW) / 2;
                            const userFlowFormat = (imgData.dataUrl && imgData.dataUrl.startsWith('data:image/png')) ? 'PNG' : 'JPEG';
                            doc.addImage(imgData.dataUrl, userFlowFormat, offsetX + 3, y + 3, imgW - 6, imgH, undefined, 'FAST');
                            y += imgH + 10;
                        } else {
                            // Fallback placeholder if render failed
                            checkPage(25);
                            doc.setFillColor(...lightBg);
                            doc.roundedRect(marginLeft, y, contentWidth, 22, 2, 2, 'F');
                            doc.setFillColor(...brandAccent);
                            doc.rect(marginLeft, y, 2, 22, 'F');
                            doc.setFontSize(10);
                            doc.setFont('helvetica', 'bold');
                            doc.setTextColor(...darkText);
                            doc.text('[USER FLOW DIAGRAM]', marginLeft + 8, y + 8);
                            doc.setFontSize(8);
                            doc.setFont('helvetica', 'normal');
                            doc.setTextColor(...mutedText);
                            doc.text('Visual user flow diagram available in the web interface', marginLeft + 8, y + 15);
                            y += 26;
                        }
                    } else if (codeBlockType === 'erDiagram' || codeBlockType.includes('ER') || codeBlockType.includes('schema')) {
                        // ── Embed actual rendered ER Diagram image (JPEG/PNG) ──
                        const imgData = erDiagramImages[erDiagramImageIdx++] || null;
                        if (imgData && imgData.dataUrl) {
                            let imgW = contentWidth;
                            const maxHeight = pageHeight - 65; // Leave room for margins
                            let imgH = imgW * (imgData.aspectRatio || 0.55);
                            if (imgH > maxHeight) {
                                imgH = maxHeight;
                                imgW = imgH / (imgData.aspectRatio || 0.55);
                            }
                            checkPage(imgH + 10);
                            // light background card
                            doc.setFillColor(...lightBg);
                            doc.roundedRect(marginLeft, y, contentWidth, imgH + 6, 2, 2, 'F');
                            doc.setFillColor(...brandAccent);
                            doc.rect(marginLeft, y, 2, imgH + 6, 'F');
                            const offsetX = marginLeft + (contentWidth - imgW) / 2;
                            const erFormat = (imgData.dataUrl && imgData.dataUrl.startsWith('data:image/png')) ? 'PNG' : 'JPEG';
                            doc.addImage(imgData.dataUrl, erFormat, offsetX + 3, y + 3, imgW - 6, imgH, undefined, 'FAST');
                            y += imgH + 10;
                        } else {
                            // Fallback placeholder if render failed
                            checkPage(25);
                            doc.setFillColor(...lightBg);
                            doc.roundedRect(marginLeft, y, contentWidth, 22, 2, 2, 'F');
                            doc.setFillColor(...brandAccent);
                            doc.rect(marginLeft, y, 2, 22, 'F');
                            doc.setFontSize(10);
                            doc.setFont('helvetica', 'bold');
                            doc.setTextColor(...darkText);
                            doc.text('[DATABASE SCHEMA DIAGRAM]', marginLeft + 8, y + 8);
                            doc.setFontSize(8);
                            doc.setFont('helvetica', 'normal');
                            doc.setTextColor(...mutedText);
                            doc.text('Visual database schema diagram available in the web interface', marginLeft + 8, y + 15);
                            y += 26;
                        }
                    } else {
                        // ── General / file-tree code block ──
                        // Normalize Unicode / box-drawing tree chars so jsPDF courier can render them
                        const normalizedContent = codeBlockContent.map(l => normalizeTreeChars(l));
                        // Calculate height: render all lines (paginated)
                        const lineH = 3.8;
                        const paddingV = 6;
                        const maxBlockH = pageHeight - 44; // nearly a full page at most
                        const totalCodeH = Math.min(normalizedContent.length * lineH + paddingV * 2, maxBlockH);

                        checkPage(Math.min(totalCodeH, 30));
                        doc.setFillColor(...lightBg);
                        doc.roundedRect(marginLeft, y, contentWidth, totalCodeH, 2, 2, 'F');
                        doc.setFontSize(6.5);
                        doc.setFont('courier', 'normal');
                        doc.setTextColor(...darkText);

                        let codeY = y + paddingV;
                        for (const codeLine of normalizedContent) {
                            if (codeY + lineH > y + totalCodeH - 2) break;
                            if (codeY + lineH > pageHeight - 22) {
                                // spill to next page
                                addFooter(doc.internal.getNumberOfPages());
                                doc.addPage();
                                y = 20;
                                codeY = y + paddingV;
                                doc.setFillColor(...lightBg);
                                doc.roundedRect(marginLeft, y, contentWidth, totalCodeH, 2, 2, 'F');
                                doc.setFontSize(6.5);
                                doc.setFont('courier', 'normal');
                                doc.setTextColor(...darkText);
                            }
                            // Clip very long lines
                            const printLine = codeLine.length > 110 ? codeLine.substring(0, 108) + '..' : codeLine;
                            doc.text(printLine, marginLeft + 3, codeY);
                            codeY += lineH;
                        }
                        y = codeY + paddingV;
                    }

                    codeBlockType = '';
                    codeBlockContent = [];
                    continue;
                }
            }

            // ── Skip content inside code blocks ──
            if (inCodeBlock) {
                codeBlockContent.push(line);
                continue;
            }

            // ── Detect loose folder-structure lines (tree chars that escaped a code block) ──
            // These are Unicode box-drawing chars (├, │, └, ─) or %% sequences
            const isTableRow = trimmed.includes('|') && trimmed.split('|').length >= 3;
            const isTreeLine = !isTableRow && (/^[│├└─%]/.test(trimmed) || /^[|\\+]--/.test(trimmed));
            if (isTreeLine) {
                // Collect the whole tree block, normalize, and render in monospace
                if (!skipFolderStructure) {
                    skipFolderStructure = true;
                    // Collect all consecutive tree lines
                    const treeLines = [normalizeTreeChars(line)];
                    let j = i + 1;
                    while (j < lines.length) {
                        const nextTrimmed = lines[j].trim();
                        if (!nextTrimmed) { j++; break; }
                        const nextIsTableRow = nextTrimmed.includes('|') && nextTrimmed.split('|').length >= 3;
                        if (!nextIsTableRow && (/^[│├└─%\\+]/.test(nextTrimmed) || /^[|\\+]--/.test(nextTrimmed))) {
                            treeLines.push(normalizeTreeChars(lines[j]));
                            j++;
                        } else {
                            break;
                        }
                    }
                    i = j - 1; // advance outer loop past consumed lines

                    const lineH = 3.8;
                    const paddingV = 5;
                    const blockH = Math.min(treeLines.length * lineH + paddingV * 2, pageHeight - 44);
                    checkPage(Math.min(blockH, 30));
                    doc.setFillColor(...lightBg);
                    doc.roundedRect(marginLeft, y, contentWidth, blockH, 2, 2, 'F');
                    doc.setFontSize(6.5);
                    doc.setFont('courier', 'normal');
                    doc.setTextColor(...darkText);
                    let codeY = y + paddingV;
                    for (const tl of treeLines) {
                        if (codeY + lineH > y + blockH - 2) break;
                        if (codeY + lineH > pageHeight - 22) {
                            addFooter(doc.internal.getNumberOfPages());
                            doc.addPage();
                            y = 20;
                            codeY = y + paddingV;
                            doc.setFillColor(...lightBg);
                            doc.roundedRect(marginLeft, y, contentWidth, blockH, 2, 2, 'F');
                            doc.setFontSize(6.5);
                            doc.setFont('courier', 'normal');
                            doc.setTextColor(...darkText);
                        }
                        const printLine = tl.length > 110 ? tl.substring(0, 108) + '..' : tl;
                        doc.text(printLine, marginLeft + 3, codeY);
                        codeY += lineH;
                    }
                    y = codeY + paddingV;
                }
                continue;
            } else {
                skipFolderStructure = false;
            }

            if (!trimmed) {
                y += 1.5;
                continue;
            }

            checkPage(14);

            // ── Markdown heading (# / ## / ### / ####) ──
            const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)/);
            if (headingMatch) {
                const level = headingMatch[1].length;
                const headingText = headingMatch[2].replace(/\*\*/g, '').replace(/\*/g, '');
                y += level === 1 ? 4 : level === 2 ? 3 : 2;

                checkPage(14);

                const fontSize = level === 1 ? 13 : level === 2 ? 11.5 : level === 3 ? 10 : 9.5;
                doc.setFontSize(fontSize);
                doc.setFont('helvetica', 'bold');
                doc.setTextColor(level <= 2 ? brandBlue[0] : darkText[0], level <= 2 ? brandBlue[1] : darkText[1], level <= 2 ? brandBlue[2] : darkText[2]);

                const wrappedHeading = doc.splitTextToSize(headingText, contentWidth);
                for (const hl of wrappedHeading) {
                    checkPage(8);
                    doc.text(hl, marginLeft, y);
                    y += fontSize * 0.42 + 1;
                }

                y += 1;
                continue;
            }

            // ── Bold line (**text**) ──
            const isBoldLine = /^\*\*(.+)\*\*$/.test(trimmed);

            // ── Bullet / list item ──
            const bulletMatch = trimmed.match(/^[-*•]\s+(.+)/);
            const numberedMatch = trimmed.match(/^(\d+)[.)]\s+(.+)/);

            if (bulletMatch || numberedMatch) {
                doc.setFontSize(9);
                doc.setFont('helvetica', 'normal');
                doc.setTextColor(...darkText);

                const bulletText = bulletMatch ? bulletMatch[1] : numberedMatch[2];
                const prefix = bulletMatch ? '•  ' : `${numberedMatch[1]}.  `;
                const cleanText = bulletText.replace(/\*\*/g, '').replace(/\*/g, '');

                const indentX = marginLeft + 6;
                const bulletWidth = contentWidth - 6;
                const wrapped = doc.splitTextToSize(`${prefix}${cleanText}`, bulletWidth);
                for (const wl of wrapped) {
                    checkPage(6);
                    doc.text(wl, indentX, y);
                    y += 4.5;
                }
                y += 1;
                continue;
            }

            // ── Horizontal rule ──
            if (/^[-_*]{3,}$/.test(trimmed)) {
                y += 2;
                doc.setDrawColor(220, 220, 230);
                doc.setLineWidth(0.15);
                doc.line(marginLeft, y, pageWidth - marginRight, y);
                y += 4;
                continue;
            }

            // ── Regular paragraph ──
            doc.setFontSize(9);
            doc.setFont('helvetica', isBoldLine ? 'bold' : 'normal');
            doc.setTextColor(...darkText);

            const cleanParagraph = trimmed.replace(/\*\*/g, '').replace(/\*/g, '');
            const wrapped = doc.splitTextToSize(cleanParagraph, contentWidth);
            for (const wl of wrapped) {
                checkPage(6);
                doc.text(wl, marginLeft, y);
                y += 4.5;
            }
            y += 2;
        }

        // ── Draw all footers once at the end with the correct total page count ──
        const totalPages = doc.internal.getNumberOfPages();
        for (let i = 1; i <= totalPages; i++) {
            doc.setPage(i);
            addFooter(i, totalPages);
        }

        // ── Save ──
        const fileName = `${(selectedProject?.name || result.filename || 'BRD_Analysis').replace(/[^a-zA-Z0-9_-]/g, '_')}_Report.pdf`;
        doc.save(fileName);
    };

    const handleNewAnalysis = () => {
        navigate('/dashboard');
    };



    if (error && !result) {
        return (
            <div className="h-full flex items-center justify-center bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">
                <div className="text-center max-w-md">
                    <p className="text-app-status-error font-semibold mb-4">{error}</p>
                    <button
                        onClick={() => navigate('/dashboard')}
                        className="px-4 py-2 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors"
                    >
                        Go to Dashboard
                    </button>
                </div>
            </div>
        );
    }

    if (!result && !loading && !processing) {
        return (
            <div className="h-full flex items-center justify-center bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">
                <div className="text-center max-w-md">
                    <p className="text-app-text-muted font-semibold mb-4">No analysis found for this project.</p>
                    <button
                        onClick={() => navigate('/dashboard')}
                        className="px-4 py-2 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors"
                    >
                        Go to Dashboard
                    </button>
                </div>
            </div>
        );
    }



    return (
        <div className="h-full overflow-y-auto bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">
            {/* Fixed Right Sidebar - Tabbed BRD Chat + Clarification Panel */}
            {(() => {
                const clarificationQuestions = aiQuestions?.length > 0 ? aiQuestions : (result?.analysis?.questions || []);
                const clarificationCount = clarificationQuestions.length;
                return (
                    <div
                        className={`fixed right-6 top-6 bottom-6 bg-white border border-gray-200 rounded-2xl shadow-2xl transition-all duration-300 z-[260] flex flex-col overflow-hidden ${isSidebarOpen
                            ? 'translate-x-0 opacity-100'
                            : 'translate-x-[120%] opacity-0 pointer-events-none'
                            } ${isChatExpanded ? 'w-[900px] max-w-[90vw]' : 'w-[440px]'}`}
                    >

                        {/* Sidebar Header with tabs */}
                        <div className="flex-shrink-0 bg-white border-b border-gray-200">
                            {/* Top bar: title + expand + close */}
                            <div className="flex items-center justify-between px-5 py-3">
                                <div className="flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></div>
                                    <span className="text-sm font-bold text-gray-900">BRD Assistant</span>
                                </div>
                                <div className="flex items-center gap-1.5">
                                    {/* Expand/Collapse Button */}
                                    <button
                                        onClick={() => setIsChatExpanded(prev => !prev)}
                                        title={isChatExpanded ? "Collapse panel" : "Expand panel"}
                                        className="flex items-center gap-1 text-xs font-semibold text-gray-500 hover:text-gray-900 hover:bg-gray-100 px-2.5 py-1.5 rounded-lg transition-all"
                                    >
                                        {isChatExpanded ? (
                                            <>
                                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M18 12H6" />
                                                </svg>
                                                <span>Collapse</span>
                                            </>
                                        ) : (
                                            <>
                                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                                                </svg>
                                                <span>Expand</span>
                                            </>
                                        )}
                                    </button>

                                    <button
                                        onClick={() => setIsSidebarOpen(false)}
                                        className="flex items-center gap-1.5 text-xs font-semibold text-gray-500 hover:text-gray-900 hover:bg-gray-100 px-3 py-1.5 rounded-lg transition-all"
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                        </svg>
                                        Close
                                    </button>
                                </div>
                            </div>

                            {/* Tab switcher */}
                            <div className="flex border-t border-gray-100">
                                <button
                                    onClick={() => setSidebarTab('chat')}
                                    className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-semibold transition-all ${sidebarTab === 'chat'
                                        ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/50'
                                        : 'text-gray-500 hover:text-gray-800 hover:bg-gray-50 border-b-2 border-transparent'
                                        }`}
                                >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                                    </svg>
                                    BRD Chat
                                    {chatMessages.length > 0 && (
                                        <span className="px-1.5 py-0.5 text-[10px] font-bold bg-blue-600 text-white rounded-full">{chatMessages.length}</span>
                                    )}
                                </button>
                                <button
                                    onClick={() => setSidebarTab('clarification')}
                                    className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-semibold transition-all ${sidebarTab === 'clarification'
                                        ? 'text-amber-700 border-b-2 border-amber-600 bg-amber-50/50'
                                        : 'text-gray-500 hover:text-gray-800 hover:bg-gray-50 border-b-2 border-transparent'
                                        }`}
                                >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                    </svg>
                                    Clarification
                                    {clarificationCount > 0 && (
                                        <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded-full ${sidebarTab === 'clarification' ? 'bg-amber-600 text-white' : 'bg-amber-100 text-amber-700'}`}>{clarificationCount}</span>
                                    )}
                                </button>
                            </div>
                        </div>

                        {/* ── BRD Chat Tab ── */}
                        {sidebarTab === 'chat' && (
                            <>
                                {/* Chat Message Thread */}
                                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 bg-gray-50">
                                    {/* Welcome message with suggested options */}
                                    {renderedMessages.length === 0 && (
                                        <div className="py-6 px-4 bg-white border border-gray-200 rounded-2xl shadow-sm text-center my-2">
                                            <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center mx-auto mb-3">
                                                <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                                                </svg>
                                            </div>
                                            <h4 className="text-xs font-bold text-gray-700 mb-1">BRD Refinement Assistant</h4>
                                            <p className="text-[11px] text-gray-500 mb-4 max-w-[260px] mx-auto">
                                                How would you like to enhance your requirements? Choose one of the quick options below:
                                            </p>
                                            
                                            <div className="space-y-2 text-left">
                                                <button
                                                    onClick={() => handleSuggestedOption('generate_techniques')}
                                                    className="w-full text-[11px] font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-xl px-3 py-2 text-left transition-all flex items-center gap-2 group"
                                                >
                                                    <span className="group-hover:scale-110 transition-transform">💡</span>
                                                    <span>Generate requirements elicitation techniques</span>
                                                </button>
                                                <button
                                                    onClick={() => handleSuggestedOption('identify_gaps')}
                                                    className="w-full text-[11px] font-semibold text-gray-700 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-xl px-3 py-2 text-left transition-all flex items-center gap-2 group"
                                                >
                                                    <span className="group-hover:scale-110 transition-transform">🔍</span>
                                                    <span>Identify potential edge cases and gaps</span>
                                                </button>
                                                <button
                                                    onClick={() => handleSuggestedOption('summarize_report')}
                                                    className="w-full text-[11px] font-semibold text-gray-700 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-xl px-3 py-2 text-left transition-all flex items-center gap-2 group"
                                                >
                                                    <span className="group-hover:scale-110 transition-transform">📄</span>
                                                    <span>Summarize finalized report & metrics</span>
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {/* Chat messages */}
                                    {renderedMessages.map((msg) => (
                                        <div key={msg.id} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                                            {/* Label */}
                                            <span className="text-[10px] text-gray-400 mb-1 px-1">
                                                {msg.role === 'user' ? 'You' : 'BRD Assistant'} · {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                            </span>
                                            {/* Bubble */}
                                            <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-xs leading-relaxed shadow-sm ${msg.role === 'user'
                                                ? 'bg-blue-600 text-white rounded-tr-sm'
                                                : msg.isError
                                                    ? 'bg-red-50 text-red-700 border border-red-200 rounded-tl-sm'
                                                    : 'bg-white text-gray-800 border border-gray-200 rounded-tl-sm'
                                                }`}>
                                                <div className={`prose prose-xs max-w-none ${msg.role === 'user' ? 'prose-invert text-white' : 'text-gray-800'}`}>
                                                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                                                        {msg.content}
                                                    </ReactMarkdown>
                                                </div>

                                                {/* Techniques Cards Deck inside bubble */}
                                                {msg.isElicitation && elicitationTechniques.length > 0 && (
                                                    <div className="mt-4 pt-3 border-t border-gray-100 space-y-3">
                                                        <div className="flex items-center justify-between gap-1.5 pb-1">
                                                            <span className="text-[9px] font-bold uppercase tracking-wider text-gray-400">
                                                                Refinement Techniques
                                                            </span>
                                                            <span className={`text-[8px] font-semibold px-2 py-0.5 rounded-full ${
                                                                techniquesSource === 'uploaded' 
                                                                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-100' 
                                                                    : 'bg-blue-50 text-blue-700 border border-blue-100'
                                                            }`}>
                                                                {techniquesSource === 'uploaded' ? 'Custom Skill' : 'AI SDLC Process'}
                                                            </span>
                                                        </div>
                                                        <div className="grid grid-cols-1 gap-2.5">
                                                            {elicitationTechniques.map((tech, idx) => (
                                                                <div 
                                                                    key={idx} 
                                                                    className="bg-gray-50/80 border border-gray-200/60 rounded-xl p-2.5 transition-all duration-300 flex items-center justify-between gap-3 hover:border-blue-300 hover:bg-white hover:shadow-xs group/card"
                                                                >
                                                                    {/* Left: Technique Name clickable & highlights on hover */}
                                                                    <span 
                                                                        onClick={() => handleApplyTechnique(tech)}
                                                                        className="font-bold text-gray-700 text-[11px] leading-tight group-hover/card:text-blue-600 transition-colors cursor-pointer flex-1 min-w-0 truncate"
                                                                        title={`Apply methodology: ${tech.name}`}
                                                                    >
                                                                        {tech.name}
                                                                    </span>
                                                                    
                                                                    {/* Right: Actions (Tick + Info) */}
                                                                    <div className="flex items-center gap-1.5 flex-shrink-0">
                                                                        {/* Tick / Apply Button */}
                                                                        <button
                                                                            onClick={() => handleApplyTechnique(tech)}
                                                                            disabled={chatSending || processing}
                                                                            title="Apply this method"
                                                                            className="text-gray-400 hover:text-emerald-600 hover:bg-emerald-50 bg-white border border-gray-200/80 hover:border-emerald-200 transition-all p-1 rounded-full hover:scale-105 active:scale-95 shadow-xs disabled:opacity-50 disabled:pointer-events-none flex items-center justify-center"
                                                                        >
                                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                                                            </svg>
                                                                        </button>

                                                                        {/* Info / Tooltip Button */}
                                                                        <div className="relative group/tooltip flex-shrink-0">
                                                                            <button 
                                                                                type="button"
                                                                                className="text-gray-400 hover:text-blue-600 hover:bg-blue-50 bg-white border border-gray-200/80 hover:border-blue-200 transition-all p-1 rounded-full shadow-xs focus:outline-none flex items-center justify-center"
                                                                            >
                                                                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                                                </svg>
                                                                            </button>
                                                                            {/* Tooltip Content */}
                                                                            <div className="absolute right-full -top-12 mr-3 w-64 p-3 bg-slate-900/95 text-white text-[10.5px] leading-relaxed rounded-xl shadow-xl border border-slate-800 backdrop-blur-md opacity-0 pointer-events-none group-hover/tooltip:opacity-100 group-hover/tooltip:translate-x-0 transition-all duration-300 z-50 transform translate-x-1">
                                                                                <div className="font-bold text-blue-400 mb-1 flex items-center justify-between">
                                                                                    <span>{tech.name}</span>
                                                                                    <span className="text-[8px] font-semibold uppercase tracking-wider text-gray-400 bg-slate-800 px-1.5 py-0.5 rounded">
                                                                                        {techniquesSource === 'uploaded' ? 'Custom Skill' : 'AI SDLC'}
                                                                                    </span>
                                                                                </div>
                                                                                <div className="text-gray-200 mt-1 whitespace-pre-line leading-relaxed font-normal">
                                                                                    {tech.description}
                                                                                </div>
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Affected sections badge */}
                                                {msg.affectedSections && msg.affectedSections.length > 0 && (
                                                    <div className="mt-2 pt-2 border-t border-gray-100 flex flex-wrap gap-1">
                                                        <span className="text-[10px] text-gray-400 w-full mb-1">Updated sections:</span>
                                                        {msg.affectedSections.map((s, i) => (
                                                            <span key={i} className="inline-block bg-blue-50 text-blue-700 border border-blue-100 rounded-full px-2 py-0.5 text-[10px] font-medium">
                                                                {s}
                                                            </span>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    ))}

                                    {/* Typing indicator */}
                                    {(chatSending || processing) && (
                                        <div className="flex items-start gap-2">
                                            <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
                                                <div className="flex gap-1 items-center h-4">
                                                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                                                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                                                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    <div ref={chatEndRef} />
                                </div>

                                {/* Chat Input */}
                                <div className="px-4 py-4 border-t border-gray-100 bg-white flex-shrink-0">
                                    {/* Apply discussion changes banner */}
                                    {discussMode && chatMessages.length > 0 && (
                                        <div className="mb-3 px-3 py-2 bg-blue-50 border border-blue-100 rounded-xl flex items-center justify-between gap-3 text-[11px] animate-fade-in">
                                            <span className="text-blue-700 font-medium leading-tight">
                                                Ready to write these planned changes into the BRD?
                                            </span>
                                            <button
                                                onClick={handleApplyDiscussionToBRD}
                                                disabled={chatSending || processing}
                                                className="px-2.5 py-1 text-[10px] font-bold text-white bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed rounded-lg shadow-sm transition-all whitespace-nowrap"
                                            >
                                                Apply to BRD
                                            </button>
                                        </div>
                                    )}
                                    
                                    <div className="flex items-center gap-2">
                                        <div className="flex-1">
                                            <textarea
                                                value={chatInput}
                                                onChange={(e) => {
                                                    setChatInput(e.target.value);
 
                                                    // Auto expand upward
                                                    e.target.style.height = 'auto';
                                                    e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
                                                }}
                                                onKeyDown={(e) => {
                                                    if (e.key === 'Enter' && !e.shiftKey) {
                                                        e.preventDefault();
                                                        handleChatSend();
                                                    }
                                                }}
                                                placeholder={
                                                    discussMode
                                                        ? "Ask anything, discuss requirements..."
                                                        : "Describe what to update in the BRD... (will rebuild BRD)"
                                                }
                                                rows={1}
                                                className={`block w-full px-3 py-2.5 text-xs border rounded-xl focus:ring-2 focus:outline-none resize-none placeholder-gray-400 overflow-y-auto min-h-[42px] max-h-[140px] transition-all duration-300 ${
                                                    discussMode
                                                        ? "border-gray-200 focus:ring-blue-500 focus:border-blue-500 bg-gray-50"
                                                        : "border-purple-200 focus:ring-purple-500 focus:border-purple-500 bg-purple-50/20 placeholder-purple-400/80"
                                                }`}
                                                style={{ height: '42px' }}
                                                disabled={chatSending || processing}
                                            />
                                        </div>
 
                                        <button
                                            onClick={handleChatSend}
                                            disabled={!chatInput.trim() || chatSending || processing}
                                            className={`flex-shrink-0 h-[42px] w-[42px] flex items-center justify-center text-white rounded-xl transition-all duration-300 shadow-sm ${
                                                discussMode
                                                    ? "bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600 disabled:from-gray-200 disabled:to-gray-200 disabled:cursor-not-allowed"
                                                    : "bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 disabled:from-gray-200 disabled:to-gray-200 disabled:cursor-not-allowed"
                                            }`}
                                        >
                                            <svg
                                                className="w-4 h-4"
                                                fill="none"
                                                stroke="currentColor"
                                                viewBox="0 0 24 24"
                                            >
                                                <path
                                                    strokeLinecap="round"
                                                    strokeLinejoin="round"
                                                    strokeWidth={2}
                                                    d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                                                />
                                            </svg>
                                        </button>
                                    </div>
 
                                    {/* Bottom bar for Discuss Mode toggle */}
                                    <div className="flex items-center justify-between mt-1 pt-1 border-t border-gray-100/50">
                                        <div className="relative mode-dropdown-container">
                                            <button
                                                onClick={() => setModeDropdownOpen(prev => !prev)}
                                                disabled={chatSending || processing}
                                                className={`flex items-center gap-1.5 h-7 px-3 rounded-lg border text-[10px] font-bold shadow-xs transition-all duration-200 cursor-pointer disabled:cursor-not-allowed ${
                                                    discussMode
                                                        ? 'bg-blue-50 border-blue-200 text-blue-600 hover:bg-blue-100/70'
                                                        : 'bg-purple-50 border-purple-200 text-purple-600 hover:bg-purple-100/70'
                                                }`}
                                            >
                                                {discussMode ? (
                                                    <>
                                                        <svg className="w-3.5 h-3.5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                                                        </svg>
                                                        <span>Q&A / Discuss Mode</span>
                                                    </>
                                                ) : (
                                                    <>
                                                        <svg className="w-3.5 h-3.5 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                                                        </svg>
                                                        <span>Edit BRD Mode</span>
                                                    </>
                                                )}
                                                <svg className="w-2.5 h-2.5 opacity-60 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                                </svg>
                                            </button>
 
                                            {modeDropdownOpen && (
                                                <div className="absolute left-0 bottom-full mb-2 w-64 bg-white border border-gray-150 rounded-xl shadow-lg py-1.5 z-50 animate-fade-in">
                                                    <div className="px-3 py-1 text-[9px] font-bold text-gray-400 uppercase tracking-wider">
                                                        Select Mode
                                                    </div>
                                                    
                                                    <button
                                                        onClick={() => {
                                                            setDiscussMode(false);
                                                            setModeDropdownOpen(false);
                                                        }}
                                                        className={`w-full text-left px-3 py-2 flex items-start gap-2.5 transition-all hover:bg-purple-50/50 ${
                                                            !discussMode ? 'bg-purple-50/20' : ''
                                                        }`}
                                                    >
                                                        <div className={`mt-0.5 p-1 rounded-md ${!discussMode ? 'bg-purple-100 text-purple-600' : 'bg-gray-100 text-gray-500'}`}>
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                                                            </svg>
                                                        </div>
                                                        <div>
                                                            <div className={`text-xs font-semibold ${!discussMode ? 'text-purple-900' : 'text-gray-700'}`}>
                                                                Edit BRD Mode
                                                            </div>
                                                            <div className="text-[10px] text-gray-500 mt-0.5 leading-normal">
                                                                Your prompts will directly update and rebuild the specs (takes a few minutes).
                                                            </div>
                                                        </div>
                                                    </button>
 
                                                    <button
                                                        onClick={() => {
                                                            setDiscussMode(true);
                                                            setModeDropdownOpen(false);
                                                        }}
                                                        className={`w-full text-left px-3 py-2 flex items-start gap-2.5 transition-all hover:bg-blue-50/50 ${
                                                            discussMode ? 'bg-blue-50/20' : ''
                                                        }`}
                                                    >
                                                        <div className={`mt-0.5 p-1 rounded-md ${discussMode ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-500'}`}>
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                                                            </svg>
                                                        </div>
                                                        <div>
                                                            <div className={`text-xs font-semibold ${discussMode ? 'text-blue-900' : 'text-gray-700'}`}>
                                                                Q&A / Discuss Mode
                                                            </div>
                                                            <div className="text-[10px] text-gray-500 mt-0.5 leading-normal">
                                                                Discuss and brainstorm requirements. The conversation history can be applied to update the BRD later.
                                                            </div>
                                                        </div>
                                                    </button>
                                                </div>
                                            )}
                                        </div>

                                        <div className="flex items-center gap-1.5 text-[10px] text-gray-500 font-medium">
                                            <span className={`w-1.5 h-1.5 rounded-full ${discussMode ? 'bg-blue-500 animate-pulse' : 'bg-purple-500 animate-pulse'}`}></span>
                                            <span>{discussMode ? 'Conversational mode' : 'Direct update mode'}</span>
                                        </div>
                                    </div>
                                </div>
                            </>
                        )}

                        {/* ── Clarification Needed Tab ── */}
                        {sidebarTab === 'clarification' && (
                            <div className="flex-1 overflow-y-auto flex flex-col">
                                {clarificationCount === 0 ? (
                                    <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 text-center">
                                        <div className="w-14 h-14 rounded-full bg-green-50 flex items-center justify-center mx-auto mb-4">
                                            <svg className="w-7 h-7 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                            </svg>
                                        </div>
                                        <p className="text-sm font-semibold text-gray-700 mb-1">No open questions</p>
                                        <p className="text-xs text-gray-400 leading-relaxed max-w-[240px]">
                                            The AI has no pending clarifications. All ambiguities are resolved.
                                        </p>
                                    </div>
                                ) : (
                                    <>
                                        <div className="px-5 py-4 bg-amber-50 border-b border-amber-100 flex-shrink-0">
                                            <p className="text-xs text-amber-700 leading-relaxed">
                                                Answer these questions to refine specific sections of the analysis. The AI will surgically update only affected areas.
                                            </p>
                                        </div>
                                        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3 bg-gray-50">
                                            {clarificationQuestions.map((q, i) => (
                                                <div key={i} className="bg-white rounded-xl p-4 border border-amber-100 shadow-sm">
                                                    <div className="flex items-start gap-2 mb-2">
                                                        <span className="flex-shrink-0 w-5 h-5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-bold flex items-center justify-center mt-0.5">{i + 1}</span>
                                                        <p className="text-xs font-medium text-gray-700 leading-relaxed">{q}</p>
                                                    </div>
                                                    <input
                                                        type="text"
                                                        value={userAnswers[i] || ''}
                                                        onChange={e => setUserAnswers(prev => ({ ...prev, [i]: e.target.value }))}
                                                        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleQASubmit(); } }}
                                                        className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg focus:ring-2 focus:ring-amber-400 focus:border-amber-400 bg-gray-50 placeholder-gray-400"
                                                        placeholder="Your answer..."
                                                    />
                                                </div>
                                            ))}
                                        </div>
                                        <div className="px-5 py-4 border-t border-gray-100 bg-white flex-shrink-0">
                                            <button
                                                onClick={handleQASubmit}
                                                disabled={chatSending || processing}
                                                className="w-full py-2.5 text-xs font-bold text-white bg-amber-600 hover:bg-amber-700 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                                            >
                                                {chatSending || processing ? 'Updating...' : 'Submit Answers & Update Analysis'}
                                            </button>
                                            <p className="text-[10px] text-gray-400 mt-2 text-center">Answers are applied surgically to affected sections</p>
                                        </div>
                                    </>
                                )}
                            </div>
                        )}
                    </div>
                );
            })()}

            {/* Main Content Container */}
            <div className={`transition-all duration-300 ${isSidebarOpen ? 'lg:mr-[460px]' : 'mr-0'}`}>
                <div className="max-w-[1100px] mx-auto px-12 py-6 space-y-6">
                    {/* If page is loading and we don't have a result yet */}
                    {(!result && (loading || processing)) && (
                        <div className="py-24 text-center">
                            <Loader2 className="w-12 h-12 text-app-primary animate-spin mx-auto mb-4" />
                            <p className="text-app-text-main font-semibold mb-2">
                                {progressMessage || 'Preparing analysis...'}
                            </p>
                            {progress > 0 && (
                                <div className="w-48 bg-gray-200 rounded-full h-2 mt-4 mx-auto overflow-hidden">
                                    <div
                                        className="bg-app-primary h-2 rounded-full transition-all duration-300"
                                        style={{ width: `${progress}%` }}
                                    />
                                </div>
                            )}
                        </div>
                    )}

                    {/* If result is loaded but loading is true (switching projects/fetching updates) */}
                    {(result && loading) && (
                        <div className="py-24 text-center">
                            <Loader2 className="w-8 h-8 text-app-primary animate-spin mx-auto mb-4" />
                            <p className="text-app-text-muted font-semibold">Loading Agent Analysis...</p>
                        </div>
                    )}

                    {/* Main Analysis Results */}
                    {result && !loading && (
                        <div className="space-y-6 animate-fade-in-up">
                            {/* Result Header - Redesigned */}
                            <div className="bg-gradient-to-r from-white to-gray-50 rounded-2xl shadow-md border border-gray-200 overflow-hidden">
                                {/* Top Section - File Info */}
                                <div className="flex flex-col md:flex-row md:items-center justify-between p-5 border-b border-gray-100">
                                    <div className="flex items-start gap-4 mb-4 md:mb-0 min-w-0 flex-grow md:flex-1">
                                        <div className="flex-shrink-0 w-12 h-12 bg-gradient-to-br from-emerald-400 to-green-500 rounded-xl flex items-center justify-center shadow-lg shadow-emerald-500/30">
                                            <FileText className="w-6 h-6 text-white" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <h2 className="text-xl font-bold text-gray-900 truncate mb-1" title={result.filename}>{result.filename}</h2>
                                            <div className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
                                                {selectedProject && (
                                                    <>
                                                        <span className="font-medium">{selectedProject.name}</span>
                                                        <span className="text-gray-400">•</span>
                                                    </>
                                                )}
                                                {analysisInProgress || processing ? (
                                                    <div className="flex items-center gap-1.5">
                                                        <div className="w-2.5 h-2.5 bg-amber-500 rounded-full animate-pulse"></div>
                                                        <span className="font-semibold text-amber-600">Analysis in Progress</span>
                                                    </div>
                                                ) : error ? (
                                                    <div className="flex items-center gap-1.5">
                                                        <div className="w-2 h-2 bg-rose-500 rounded-full"></div>
                                                        <span className="font-semibold text-rose-600">Analysis Failed</span>
                                                    </div>
                                                ) : !(result?.analysis || result?.techniques || result?.components) ? (
                                                    <div className="flex items-center gap-1.5">
                                                        <div className="w-2 h-2 bg-slate-400 rounded-full"></div>
                                                        <span className="font-semibold text-slate-500">Analysis Not Started</span>
                                                    </div>
                                                ) : (
                                                    <div className="flex items-center gap-1.5">
                                                        <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></div>
                                                        <span className="font-medium text-emerald-600">Analysis Complete</span>
                                                    </div>
                                                )}
                                                {/* Project-type badge — derived from AI analysis metrics */}
                                                {(result?.analysis?.metrics?.project_type || result?.metrics?.project_type) && (() => {
                                                    const pt = String(result?.analysis?.metrics?.project_type || result?.metrics?.project_type || '').toLowerCase();
                                                    const isBrownfield = pt === 'brownfield';
                                                    const isMigration = pt === 'modernization' || pt === 'migration';
                                                    const isGreenfield = pt === 'greenfield';
                                                    if (!isBrownfield && !isMigration && !isGreenfield) return null;
                                                    const label = isBrownfield ? 'Brownfield' : isMigration ? 'Migration' : 'Greenfield';
                                                    const icon = isBrownfield ? '🟠' : isMigration ? '🔵' : '🟢';
                                                    const badgeCls = isBrownfield
                                                        ? 'bg-amber-50 border-amber-300 text-amber-700'
                                                        : isMigration
                                                            ? 'bg-blue-50 border-blue-300 text-blue-700'
                                                            : 'bg-emerald-50 border-emerald-300 text-emerald-700';
                                                    return (
                                                        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full border text-xs font-bold tracking-wide ${badgeCls}`} title={`Project type: ${label}`}>
                                                            <span className="text-sm leading-none">{icon}</span>
                                                            {label}
                                                        </span>
                                                    );
                                                })()}
                                            </div>
                                        </div>
                                    </div>

                                    {/* Action Buttons - Right Side */}
                                    {!isSidebarOpen && (
                                        <div className="flex items-center gap-2">
                                            <button
                                                onClick={handleDownloadPDF}
                                                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold text-gray-700 bg-white hover:bg-gray-50 border border-gray-300 rounded-lg transition-all hover:shadow-md"
                                                title="Download PDF Report"
                                            >
                                                <Download className="w-4 h-4" />
                                                <span className="hidden sm:inline">Download PDF</span>
                                            </button>
                                            <button
                                                onClick={handleNewAnalysis}
                                                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 rounded-lg transition-all hover:shadow-lg shadow-blue-500/30"
                                            >
                                                <Plus className="w-4 h-4" />
                                                <span className="hidden sm:inline">New Analysis</span>
                                            </button>
                                        </div>
                                    )}
                                </div>

                                {/* Revision Checkpoints Selector Bar */}
                                {(() => {
                                    const processedDocs = getProcessedProjectDocuments(selectedProject);
                                    const completedRevisions = processedDocs
                                        .map(doc => ({ doc, parsed: parseStoredDocumentAnalysis(doc) }))
                                        .filter(item => hasCompletedStoredAnalysis(item.parsed) || item.doc.is_virtual)
                                        .sort((a, b) => {
                                            const revA = a.doc.revision_number || a.parsed?.projectMeta?.revision_number || 1;
                                            const revB = b.doc.revision_number || b.parsed?.projectMeta?.revision_number || 1;
                                            return revA - revB;
                                        });

                                    if (completedRevisions.length <= 1) return null;

                                    return (
                                        <div className="px-5 py-3 border-t border-gray-100 bg-blue-50/40 flex flex-wrap items-center justify-between gap-3">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <span className="text-xs font-bold text-gray-500 uppercase tracking-wider flex items-center gap-1">
                                                    <span>📍 Revision Checkpoints:</span>
                                                </span>
                                                <div className="flex items-center gap-1.5 flex-wrap">
                                                    {completedRevisions.map(({ doc, parsed }) => {
                                                        const revNum = doc.revision_number || parsed?.projectMeta?.revision_number || 1;
                                                        const isSelected = result?.id === doc.id || (!result?.id && revNum === completedRevisions.length);
                                                        return (
                                                            <button
                                                                key={doc.id}
                                                                type="button"
                                                                onClick={() => handleSelectRevisionDoc(doc)}
                                                                className={`px-3 py-1 rounded-xl text-xs font-semibold transition-all flex items-center gap-1.5 ${
                                                                    isSelected
                                                                        ? 'bg-blue-600 text-white shadow-sm ring-2 ring-blue-500/20'
                                                                        : 'bg-white text-gray-700 hover:bg-gray-100 border border-gray-200'
                                                                }`}
                                                            >
                                                                <span>Rev {revNum} Checkpoint</span>
                                                                {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span>}
                                                            </button>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })()}

                                {/* Bottom Section - Interactive Buttons */}
                                <div className="flex flex-wrap items-center gap-3 px-5 py-3 bg-gray-50/50">
                                    {/* BRD Chat Button */}
                                    <button
                                        onClick={() => { setSidebarTab('chat'); setIsSidebarOpen(true); }}
                                        className={`flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg transition-all ${isSidebarOpen && sidebarTab === 'chat'
                                            ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
                                            : 'bg-white text-blue-600 border border-blue-200 hover:bg-blue-50 hover:border-blue-300'
                                            }`}
                                        title="Open BRD Chat"
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                                        </svg>
                                        <span>BRD Chat</span>
                                        {chatMessages.length > 0 && (
                                            <span className={`px-2 py-0.5 text-xs font-bold rounded-full ${isSidebarOpen && sidebarTab === 'chat' ? 'bg-white text-blue-600' : 'bg-blue-600 text-white'
                                                }`}>{chatMessages.length}</span>
                                        )}
                                    </button>

                                    {/* Clarification Button */}
                                    {(() => {
                                        const qCount = (aiQuestions?.length > 0 ? aiQuestions : (result?.analysis?.questions || [])).length;
                                        return (
                                            <button
                                                onClick={() => { setSidebarTab('clarification'); setIsSidebarOpen(true); }}
                                                className={`flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg transition-all ${isSidebarOpen && sidebarTab === 'clarification'
                                                    ? 'bg-amber-600 text-white shadow-lg shadow-amber-500/30'
                                                    : 'bg-white text-amber-600 border border-amber-200 hover:bg-amber-50 hover:border-amber-300'
                                                    }`}
                                                title="Clarification Needed"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                </svg>
                                                <span>Clarification</span>
                                                {qCount > 0 && (
                                                    <span className={`px-2 py-0.5 text-xs font-bold rounded-full ${isSidebarOpen && sidebarTab === 'clarification' ? 'bg-white text-amber-600' : 'bg-amber-600 text-white'
                                                        }`}>{qCount}</span>
                                                )}
                                            </button>
                                        );
                                    })()}

                                    {/* Extra Actions when Sidebar is Open */}
                                    {isSidebarOpen && (
                                        <>
                                            <button
                                                onClick={handleDownloadPDF}
                                                className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-all"
                                            >
                                                <Download className="w-4 h-4" />
                                                <span>Download PDF</span>
                                            </button>

                                            <button
                                                onClick={handleNewAnalysis}
                                                className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-gradient-to-r from-blue-600 to-blue-700 rounded-lg hover:from-blue-700 hover:to-blue-800 transition-all"
                                            >
                                                <Plus className="w-4 h-4" />
                                                <span>New Analysis</span>
                                            </button>
                                        </>
                                    )}
                                </div>
                            </div>

                            {hasGovernanceAssessment && !processing && result?.analysis?.analysis && String(result.analysis.analysis).trim().length > 0 && (
                                <div className="bg-gradient-to-r from-app-status-warningBg to-orange-50 rounded-xl shadow-sm border border-amber-200/60 p-5 flex flex-col sm:flex-row items-center justify-between gap-4">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-amber-400 to-app-status-warning flex items-center justify-center shadow-lg shadow-amber-200">
                                            <KeyRound className="w-5 h-5 text-white" />
                                        </div>
                                        <div>
                                            <h3 className="text-sm font-bold text-amber-900">Prerequisite Classification</h3>
                                            <p className="text-xs text-app-status-warning">Review AI-identified prerequisites, credentials, and access requirements before task creation.</p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => navigate('/prerequisites')}
                                        className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-bold text-white bg-gradient-to-r from-app-status-warning to-orange-500 rounded-lg shadow-lg shadow-app-status-warning/30 hover:shadow-app-status-warning/50 hover:-translate-y-0.5 transition-all active:scale-95 flex-shrink-0"
                                    >
                                        <KeyRound className="w-4 h-4" />
                                        Review Prerequisites
                                    </button>
                                </div>
                            )}

                            {/* Revision Delta & Comparison Analysis Card + Pivot Alert */}
                            {(() => {
                                const allDocs = selectedProject?.documents || [];
                                const isRev2Plus = (result?.analysis?.projectMeta?.revision_number || result?.revisionNumber || 1) > 1 || allDocs.length > 1;
                                
                                if (!isRev2Plus) return null;

                                // Smart dynamic revision delta computer
                                const sortedDocs = allDocs.slice().sort((a, b) => {
                                    const revA = parseStoredDocumentAnalysis(a)?.projectMeta?.revision_number || 1;
                                    const revB = parseStoredDocumentAnalysis(b)?.projectMeta?.revision_number || 1;
                                    return revA - revB;
                                });

                                const currentDoc = sortedDocs.find(d => d.id === result?.id) || sortedDocs[sortedDocs.length - 1];
                                const currentIndex = sortedDocs.findIndex(d => d.id === currentDoc?.id);
                                
                                // If viewing Rev 1 (index 0), don't show delta
                                if (currentIndex <= 0 && (!result?.analysis?.revision_delta)) return null;

                                const prevDoc = currentIndex > 0 ? sortedDocs[currentIndex - 1] : null;
                                const prevTitle = prevDoc?.filename || `Revision ${currentIndex}`;
                                const currTitle = currentDoc?.filename || result?.filename || `Revision ${currentIndex + 1}`;
                                const revNum = currentDoc ? (parseStoredDocumentAnalysis(currentDoc)?.projectMeta?.revision_number || currentIndex + 1) : (result?.revisionNumber || 2);

                                const storedDelta = result?.analysis?.revision_delta;

                                let comparisonSummary = storedDelta?.comparison_summary || `Revision ${revNum} checkpoint evaluation comparing '${currTitle}' against Revision ${currentIndex} ('${prevTitle}').`;
                                let overriddenFeatures = storedDelta?.overridden_features || [];
                                let newFeatures = storedDelta?.new_features || [];
                                let pivotRecommended = storedDelta?.pivot_recommended || false;
                                let pivotReason = storedDelta?.pivot_reason || '';

                                // If stored delta items are missing, dynamically parse document text differences
                                if (overriddenFeatures.length === 0 || newFeatures.length === 0) {
                                    const prevText = prevDoc?.full_content || '';
                                    const currText = currentDoc?.full_content || result?.extraction?.markdown || '';

                                    const lines = currText.split('\n').map(l => l.trim()).filter(l => l.length > 5);
                                    const prevLower = prevText.toLowerCase();

                                    const newExtracted = [];
                                    const modifiedExtracted = [];

                                    lines.forEach(l => {
                                        const clean = l.replace(/^[#\-*•\d.]+\s*/, '').trim();
                                        if (clean.length > 8 && clean.length < 120 && !clean.includes('---')) {
                                            if (!prevLower.includes(clean.toLowerCase().substring(0, 15))) {
                                                if (l.toLowerCase().includes('update') || l.toLowerCase().includes('change') || l.toLowerCase().includes('modify')) {
                                                    modifiedExtracted.push(clean);
                                                } else {
                                                    newExtracted.push(clean);
                                                }
                                            }
                                        }
                                    });

                                    if (modifiedExtracted.length > 0) overriddenFeatures = modifiedExtracted.slice(0, 4);
                                    if (newExtracted.length > 0) newFeatures = newExtracted.slice(0, 5);

                                    // Domain shift detection
                                    if (prevText && currText) {
                                        const prevSub = prevTitle.replace(/\.[^/.]+$/, "").toLowerCase();
                                        const currSub = currTitle.replace(/\.[^/.]+$/, "").toLowerCase();
                                        if (prevSub && currSub && prevSub !== currSub && !currText.toLowerCase().includes(prevSub)) {
                                            pivotRecommended = true;
                                            pivotReason = `Revision ${revNum} ('${currTitle}') differs fundamentally in product scope from Revision ${currentIndex} ('${prevTitle}'). We recommend starting a new standalone project.`;
                                        }
                                    }
                                }

                                // Dynamic fallbacks matching actual file titles if lists remain empty
                                if (overriddenFeatures.length === 0) {
                                    overriddenFeatures = [
                                        `Replaced requirement baseline from Revision ${currentIndex} ('${prevTitle}')`,
                                        `Updated UI layout & component architecture for '${currTitle}'`
                                    ];
                                }
                                if (newFeatures.length === 0) {
                                    newFeatures = [
                                        `Introduced requirement specifications from '${currTitle}'`,
                                        `Added visual layout metrics & component interaction parameters`
                                    ];
                                }

                                return (
                                    <div className="space-y-4 animate-fade-in">
                                        {/* Project Pivot Recommendation Alert */}
                                        {pivotRecommended && (
                                            <div className="p-4 bg-gradient-to-r from-amber-500/10 via-amber-400/5 to-orange-500/10 border border-amber-400/40 rounded-2xl shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                                                <div className="flex items-start gap-3">
                                                    <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center flex-shrink-0 text-xl">
                                                        💡
                                                    </div>
                                                    <div>
                                                        <h4 className="text-sm font-bold text-amber-900">
                                                            AI Strategic Recommendation: Project Pivot Alert
                                                        </h4>
                                                        <p className="text-xs text-amber-800 leading-relaxed mt-0.5 max-w-2xl">
                                                            {pivotReason || `Revision ${revNum} differs fundamentally from Revision ${currentIndex}. To maintain clean architecture, we recommend creating a standalone new project.`}
                                                        </p>
                                                    </div>
                                                </div>
                                                {/* <button
                                                    type="button"
                                                    onClick={() => {
                                                        navigate('/?create_new_project=true');
                                                    }}
                                                    className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-xl text-xs font-bold shadow-sm transition-all whitespace-nowrap flex-shrink-0"
                                                >
                                                    + Create Standalone Project
                                                </button> */}
                                            </div>
                                        )}

                                        {/* Revision Delta & Comparison Card */}
                                        <div className="bg-white rounded-2xl p-5 border border-blue-100 shadow-sm space-y-3">
                                            <div className="flex items-center justify-between border-b border-gray-100 pb-3">
                                                <div className="flex items-center gap-2">
                                                    <span className="w-2.5 h-2.5 rounded-full bg-blue-600"></span>
                                                    <h3 className="text-sm font-bold text-gray-900">
                                                        Revision {revNum} Comparison & Delta Analysis
                                                    </h3>
                                                </div>
                                                <span className="px-2.5 py-0.5 bg-blue-50 text-blue-700 rounded-full text-[11px] font-semibold border border-blue-200">
                                                    Checkpoint Analysis
                                                </span>
                                            </div>

                                            <p className="text-xs text-gray-600 leading-relaxed">
                                                {comparisonSummary}
                                            </p>

                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                                                {/* Overridden / Modified Requirements */}
                                                <div className="p-3 bg-gray-50 rounded-xl border border-gray-200/60 space-y-1.5">
                                                    <h4 className="text-[11px] font-bold text-gray-700 uppercase tracking-wider flex items-center gap-1">
                                                        <span>🔄 Modified / Overridden Items</span>
                                                    </h4>
                                                    <ul className="space-y-1">
                                                        {overriddenFeatures.map((item, idx) => (
                                                            <li key={idx} className="text-xs text-gray-600 flex items-start gap-1.5">
                                                                <span className="text-blue-500 font-bold">•</span>
                                                                <span>{item}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </div>

                                                {/* Newly Introduced Features */}
                                                <div className="p-3 bg-emerald-50/50 rounded-xl border border-emerald-200/60 space-y-1.5">
                                                    <h4 className="text-[11px] font-bold text-emerald-800 uppercase tracking-wider flex items-center gap-1">
                                                        <span>➕ Newly Added Capabilities</span>
                                                    </h4>
                                                    <ul className="space-y-1">
                                                        {newFeatures.map((item, idx) => (
                                                            <li key={idx} className="text-xs text-emerald-900 flex items-start gap-1.5">
                                                                <span className="text-emerald-600 font-bold">+</span>
                                                                <span>{item}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })()}

                            <div id="analysis-content" className="bg-transparent space-y-6">
                                {/* Stage-Based Progress Loader */}
                                {processing && (
                                    <div className="bg-app-bg-card rounded-xl border border-app-border p-6 space-y-4">
                                        <div className="flex items-center justify-between mb-4">
                                            <h3 className="text-lg font-bold text-app-text-main">Analysis in Progress</h3>
                                        </div>


                                        {/* Overall Progress Bar */}
                                        <div className="mt-4 space-y-2">
                                            {(() => {
                                                const isFinalizing = processing && progress >= 100 && !result?.analysis?.analysis;
                                                const displayProgress = isFinalizing ? 98 : progress;
                                                const displayMessage = isFinalizing
                                                    ? 'Finalizing analysis and design specifications...'
                                                    : progressMessage;
                                                return (
                                                    <>
                                                        <div className="flex justify-between items-center text-xs text-app-text-muted">
                                                            <span>{displayMessage}</span>
                                                            <span className="font-semibold">{displayProgress}%</span>
                                                        </div>
                                                        <div className="w-full bg-app-bg-muted rounded-full h-2 overflow-hidden">
                                                            <div
                                                                className="bg-gradient-to-r from-app-primary to-app-primary-hover h-2 rounded-full transition-all duration-500 ease-out shadow-[0_0_10px_rgba(37,99,235,0.5)]"
                                                                style={{ width: `${displayProgress}%` }}
                                                            ></div>
                                                        </div>
                                                    </>
                                                );
                                            })()}
                                        </div>
                                    </div>
                                )}

                                {error && !processing && !analysisInProgress && (
                                    <div className="mt-4 rounded-lg border border-red-200 bg-app-status-errorBg px-4 py-3">
                                        <p className="text-sm font-medium text-app-status-error">{error}</p>
                                    </div>
                                )}

                                {/* Key Metrics Row */}
                                {result.analysis && (
                                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                                        {(() => {
                                            const metrics = result.analysis.metrics || {};
                                            const metricItems = [
                                                { label: 'Deployment', value: metrics?.deployment || 'TBD', icon: Server, color: 'text-app-primary', bg: 'bg-app-primary-light' },
                                                { label: 'Resources', value: metrics?.resources || 'TBD', icon: Users, color: 'text-purple-600', bg: 'bg-purple-50' },
                                                { label: 'Complexity', value: metrics?.complexity || 'TBD', icon: Activity, color: 'text-orange-600', bg: 'bg-orange-50' },
                                                { label: 'Timeline (For Developer Only Mode)', value: metrics?.timeline || 'TBD', icon: Clock, color: 'text-app-status-success', bg: 'bg-app-status-successBg' }
                                            ];

                                            return metricItems.map((metric, idx) => (
                                                <div key={idx} className="bg-app-bg-card p-4 rounded-xl border border-app-border-light shadow-sm flex flex-col justify-between hover:shadow-md transition-shadow">
                                                    <div className="flex items-center justify-between mb-2">
                                                        <div className={`p-2 ${metric.bg} rounded-lg`}>
                                                            <metric.icon className={`w-4 h-4 ${metric.color}`} />
                                                        </div>
                                                    </div>
                                                    <div>
                                                        <p className="text-[10px] uppercase tracking-wider font-semibold text-app-text-light">{metric.label}</p>
                                                        <p className="text-sm font-bold text-app-text-main line-clamp-2 leading-tight" title={metric.value}>
                                                            {metric.value}
                                                        </p>
                                                    </div>
                                                </div>
                                            ));
                                        })()}
                                    </div>
                                )}

                                {/* Main Content with Fixed Right Sidebar */}
                                <div className="relative">
                                    {/* Main Content Area - Add right margin when sidebar is open */}
                                    <div>
                                        {/* Design & Analysis Tab Switcher Bar */}
                                        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200/80 pb-3 mb-5">
                                            {/* Tab Buttons */}
                                            <div className="flex items-center gap-1.5 p-1 bg-gray-100/90 rounded-xl border border-gray-200/60 shadow-inner">
                                                <button
                                                    onClick={() => setActiveDesignTab('executive')}
                                                    className={`flex items-center gap-2 px-3.5 py-2 text-xs font-bold rounded-lg transition-all ${
                                                        activeDesignTab === 'executive'
                                                            ? 'bg-white text-blue-600 shadow-sm ring-1 ring-black/5'
                                                            : 'text-gray-600 hover:text-gray-900 hover:bg-white/50'
                                                    }`}
                                                >
                                                    <FileText className="w-3.5 h-3.5" />
                                                    <span>Executive Summary</span>
                                                </button>

                                                <button
                                                    onClick={() => {
                                                        setActiveDesignTab('hld');
                                                        if (!hldDesign) {
                                                            if (result?.analysis?.hld) {
                                                                setHldDesign(result.analysis.hld);
                                                            } else if (result?.id) {
                                                                fetchArchitectureDesign(result.id);
                                                            }
                                                        }
                                                    }}
                                                    className={`flex items-center gap-2 px-3.5 py-2 text-xs font-bold rounded-lg transition-all ${
                                                        activeDesignTab === 'hld'
                                                            ? 'bg-white text-blue-600 shadow-sm ring-1 ring-black/5'
                                                            : 'text-gray-600 hover:text-gray-900 hover:bg-white/50'
                                                    }`}
                                                >
                                                    {hldDesign ? (
                                                         <Layers className="w-3.5 h-3.5 text-blue-600" />
                                                    ) : specStatus?.hld === 'generating' ? (
                                                         <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />
                                                    ) : specStatus?.hld === 'failed' ? (
                                                         <AlertCircle className="w-3.5 h-3.5 text-rose-500" />
                                                    ) : (
                                                         <Clock className="w-3.5 h-3.5 text-gray-400" />
                                                    )}
                                                    <span>High-Level Design (HLD)</span>
                                                    {hldDesign ? (
                                                        <span className="px-1.5 py-0.5 text-[9px] uppercase tracking-wide font-bold rounded bg-emerald-100 text-emerald-700">Ready</span>
                                                    ) : specStatus?.hld === 'generating' ? (
                                                        <span className="px-1.5 py-0.5 text-[9px] uppercase tracking-wide font-bold rounded bg-blue-100 text-blue-700 animate-pulse">Generating</span>
                                                    ) : specStatus?.hld === 'failed' ? (
                                                        <span className="px-1.5 py-0.5 text-[9px] uppercase tracking-wide font-bold rounded bg-rose-100 text-rose-700">Failed</span>
                                                    ) : (
                                                        <span className="px-1.5 py-0.5 text-[9px] uppercase tracking-wide font-bold rounded bg-gray-200 text-gray-700">Pending</span>
                                                    )}
                                                </button>

                                                <button
                                                    onClick={() => {
                                                        setActiveDesignTab('lld');
                                                        if (!lldDesign) {
                                                            if (result?.analysis?.lld) {
                                                                setLldDesign(result.analysis.lld);
                                                            } else if (result?.id) {
                                                                fetchArchitectureDesign(result.id);
                                                            }
                                                        }
                                                    }}
                                                    className={`flex items-center gap-2 px-3.5 py-2 text-xs font-bold rounded-lg transition-all ${
                                                        activeDesignTab === 'lld'
                                                            ? 'bg-white text-indigo-600 shadow-sm ring-1 ring-black/5'
                                                            : 'text-gray-600 hover:text-gray-900 hover:bg-white/50'
                                                    }`}
                                                >
                                                    {lldDesign ? (
                                                        <Database className="w-3.5 h-3.5 text-indigo-600" />
                                                    ) : specStatus?.lld === 'generating' ? (
                                                        <Loader2 className="w-3.5 h-3.5 text-indigo-500 animate-spin" />
                                                    ) : specStatus?.lld === 'failed' ? (
                                                        <AlertCircle className="w-3.5 h-3.5 text-rose-500" />
                                                    ) : (
                                                        <Clock className="w-3.5 h-3.5 text-gray-400" />
                                                    )}
                                                    <span>Low-Level Design (LLD)</span>
                                                    {lldDesign ? (
                                                        <span className="px-1.5 py-0.5 text-[9px] uppercase tracking-wide font-bold rounded bg-emerald-100 text-emerald-700">Ready</span>
                                                    ) : specStatus?.lld === 'generating' ? (
                                                        <span className="px-1.5 py-0.5 text-[9px] uppercase tracking-wide font-bold rounded bg-indigo-100 text-indigo-700 animate-pulse">Generating</span>
                                                    ) : specStatus?.lld === 'failed' ? (
                                                        <span className="px-1.5 py-0.5 text-[9px] uppercase tracking-wide font-bold rounded bg-rose-100 text-rose-700">Failed</span>
                                                    ) : (
                                                        <span className="px-1.5 py-0.5 text-[9px] uppercase tracking-wide font-bold rounded bg-gray-200 text-gray-700">Queued</span>
                                                    )}
                                                </button>
                                            </div>

                                            {/* Design Actions (Download PDF, Download Markdown) */}
                                            {(activeDesignTab === 'hld' || activeDesignTab === 'lld') && (
                                                <div className="flex items-center gap-2">
                                                    <button
                                                        onClick={() => handleDownloadArchitectureMarkdown(activeDesignTab)}
                                                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-all shadow-sm"
                                                        title={`Download ${activeDesignTab.toUpperCase()} Markdown`}
                                                    >
                                                        <Download className="w-3.5 h-3.5 text-blue-600" />
                                                        <span>Export Markdown</span>
                                                    </button>

                                                    <button
                                                        onClick={() => handleDownloadArchitecturePDF(activeDesignTab)}
                                                        disabled={!!exportingPdfType}
                                                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed rounded-lg transition-all shadow-sm shadow-blue-500/20"
                                                        title={`Download ${activeDesignTab.toUpperCase()} PDF`}
                                                    >
                                                        {exportingPdfType === activeDesignTab ? (
                                                            <>
                                                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                                <span>Exporting...</span>
                                                            </>
                                                        ) : (
                                                            <>
                                                                <Download className="w-3.5 h-3.5" />
                                                                <span>Export PDF</span>
                                                            </>
                                                        )}
                                                    </button>
                                                </div>
                                            )}
                                        </div>

                                        {/* ── VIEW 1: EXECUTIVE SUMMARY ── */}
                                        {activeDesignTab === 'executive' && (
                                            <>
                                                <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4 sm:p-6">
                                                    <h3 className="text-lg font-bold text-app-text-main mb-4 pb-2 border-b-2 border-app-border-light">
                                                        Executive Summary & Agent Analysis
                                                    </h3>
                                                    <div className="prose prose-lg prose-slate max-w-none text-app-text-label leading-relaxed">
                                                        {(() => {
                                                            const analysisContent = result.analysis?.analysis || '';
                                                            const explicitHtml = result.analysis?.html;
                                                            const htmlToRender = explicitHtml || (isLikelyHtml(analysisContent) ? analysisContent : null);

                                                            // Function to filter content for frontend display (hide ER diagrams and API sections)
                                                            const filterContentForDisplay = (content) => {
                                                                if (!content) return '';

                                                                const lines = content.split('\n');
                                                                const result = [];
                                                                let inCodeBlock = false;
                                                                let codeBlockType = '';
                                                                let skipSection = false;
                                                                let sectionLevel = 0;

                                                                for (let i = 0; i < lines.length; i++) {
                                                                    const line = lines[i];
                                                                    const trimmed = line.trim();

                                                                    // Detect section headers to skip
                                                                    const headerMatch = trimmed.match(/^(#{1,6})\s+(.+)/);
                                                                    if (headerMatch) {
                                                                        const level = headerMatch[1].length;
                                                                        const headerText = headerMatch[2].toLowerCase();

                                                                        // Check if this is a section we want to hide
                                                                        const shouldHide =
                                                                            headerText.includes('api specification') ||
                                                                            headerText.includes('api endpoint') ||
                                                                            headerText.includes('core api') ||
                                                                            headerText.includes('deliverable mapping') ||
                                                                            headerText.includes('files to create') ||
                                                                            headerText.includes('phase 1:') ||
                                                                            headerText.includes('phase 2:') ||
                                                                            headerText.includes('phase 3:') ||
                                                                            headerText.includes('phase 4:') ||
                                                                            headerText.includes('phase 5:') ||
                                                                            (headerText.match(/^\d+\.\d+/) && (
                                                                                headerText.includes('api') ||
                                                                                headerText.includes('deliverable')
                                                                            ));

                                                                        if (shouldHide) {
                                                                            skipSection = true;
                                                                            sectionLevel = level;
                                                                            continue;
                                                                        } else if (skipSection && level <= sectionLevel) {
                                                                            // End of skipped section - new section at same or higher level
                                                                            skipSection = false;
                                                                            sectionLevel = 0;
                                                                        }
                                                                    }

                                                                    // Skip lines if we're in a hidden section
                                                                    if (skipSection) {
                                                                        continue;
                                                                    }

                                                                    // Handle code blocks
                                                                    if (trimmed.startsWith('```')) {
                                                                        if (!inCodeBlock) {
                                                                            // Start of code block
                                                                            inCodeBlock = true;
                                                                            codeBlockType = trimmed.substring(3).trim().toLowerCase();
                                                                            result.push(line);
                                                                        } else {
                                                                            // End of code block
                                                                            inCodeBlock = false;
                                                                            codeBlockType = '';
                                                                            result.push(line);
                                                                        }
                                                                        continue;
                                                                    }

                                                                    result.push(line);
                                                                }

                                                                return result.join('\n');
                                                            };

                                                            if (processing && !analysisContent.trim()) {
                                                                return (
                                                                    <div className="text-sm text-app-text-muted italic">
                                                                        Generating analysis...
                                                                    </div>
                                                                );
                                                            }

                                                            // Always use ReactMarkdown for consistent formatting
                                                            return (
                                                                <ReactMarkdown
                                                                    remarkPlugins={[remarkGfm]}
                                                                    components={markdownComponents}
                                                                >
                                                                    {filterContentForDisplay(analysisContent)}
                                                                </ReactMarkdown>
                                                            );
                                                        })()}
                                                    </div>
                                                </div>

                                                {/* Raw Source (Collapsed) */}
                                                <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4 mt-6">
                                                    <details className="group">
                                                        <summary className="flex justify-between items-center font-medium cursor-pointer list-none text-xs text-app-text-light uppercase tracking-widest hover:text-app-text-label transition-colors">
                                                            <span>View Processed Content</span>
                                                            <span className="transition-transform group-open:rotate-180">
                                                                <svg fill="none" height="16" shapeRendering="geometricPrecision" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" viewBox="0 0 24 24" width="16"><path d="M6 9l6 6 6-6"></path></svg>
                                                            </span>
                                                        </summary>
                                                        <div className="mt-4 pt-4 border-t border-app-bg-page">
                                                            {(() => {
                                                                // Check if we have structured sections
                                                                const sections = result.analysis?.sections || result.extraction?.sections;
                                                                const markdown = result.extraction?.markdown || '';

                                                                // If we have sections OR markdown with section separators, show tabs
                                                                if ((sections && sections.length > 0) || markdown.includes('---')) {
                                                                    return <ProcessedContentTabs sections={sections} markdown={markdown} />;
                                                                }

                                                                // Fallback to HTML iframe if available
                                                                if (result.extraction?.html) {
                                                                    return (
                                                                        <div className="bg-app-bg-card rounded-lg border border-app-border overflow-hidden">
                                                                            <iframe
                                                                                srcDoc={result.extraction.html}
                                                                                className="w-full h-[420px] sm:h-[520px] lg:h-[600px] border-0"
                                                                                title="Processed Content"
                                                                                sandbox="allow-same-origin allow-scripts"
                                                                            />
                                                                        </div>
                                                                    );
                                                                }

                                                                // Final fallback to plain markdown
                                                                return (
                                                                    <div className="bg-app-bg-page rounded-lg p-4 text-xs font-mono text-app-text-label max-h-96 overflow-y-auto whitespace-pre-wrap border border-app-border-light">
                                                                        {markdown || '(No content extracted)'}
                                                                    </div>
                                                                );
                                                            })()}
                                                        </div>
                                                    </details>
                                                </div>
                                            </>
                                        )}

                                        {/* ── VIEW 2: HIGH-LEVEL DESIGN (HLD) ── */}
                                        {activeDesignTab === 'hld' && (
                                            <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4 sm:p-6 space-y-6">
                                                {/* Simple Header Bar */}
                                                <div className="pb-4 border-b border-gray-200/80">
                                                    <h2 className="text-xl font-extrabold text-gray-900">
                                                        {hldDesign?.title || `High-Level Design Specification`}
                                                    </h2>
                                                    <p className="text-xs text-gray-500 mt-0.5">
                                                        System context, C4 container topology, sequence workflows, and security matrix.
                                                    </p>
                                                </div>

                                                {/* Architecture Validation & Traceability Indicators */}
                                                {(hldDesign?.validation || hldDesign?.coverage || lldDesign?.consistency) && (
                                                    <div className="flex flex-wrap items-center gap-2 p-3 bg-gradient-to-r from-blue-50/70 via-indigo-50/50 to-slate-50/70 border border-blue-100 rounded-lg text-xs">
                                                        {hldDesign?.coverage && (
                                                            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-white border border-blue-200/80 rounded-md font-semibold text-blue-800 shadow-xs">
                                                                <span className="text-gray-500 font-normal">Architecture Coverage:</span>
                                                                <span className="font-bold text-blue-700">{hldDesign.coverage.coverage_percentage}%</span>
                                                                <span className="text-[10px] text-gray-400">({hldDesign.coverage.covered_requirements}/{hldDesign.coverage.total_requirements})</span>
                                                            </div>
                                                        )}

                                                        {hldDesign?.validation && (
                                                            <div className={`inline-flex items-center gap-1 px-2.5 py-1 bg-white border rounded-md font-semibold shadow-xs ${
                                                                hldDesign.validation.status === 'PASS' ? 'border-emerald-200 text-emerald-700' : 'border-amber-200 text-amber-700'
                                                            }`}>
                                                                <span className="text-gray-500 font-normal">HLD Validation:</span>
                                                                <span className="font-bold">{hldDesign.validation.status}</span>
                                                            </div>
                                                        )}

                                                        {lldDesign?.consistency && (
                                                            <div className={`inline-flex items-center gap-1 px-2.5 py-1 bg-white border rounded-md font-semibold shadow-xs ${
                                                                lldDesign.consistency.status === 'PASS' ? 'border-emerald-200 text-emerald-700' : 'border-amber-200 text-amber-700'
                                                            }`}>
                                                                <span className="text-gray-500 font-normal">HLD ↔ LLD:</span>
                                                                <span className="font-bold">{lldDesign.consistency.status}</span>
                                                            </div>
                                                        )}

                                                        {(() => {
                                                            const warnCount = (hldDesign?.validation?.warnings?.length || 0) + (lldDesign?.consistency?.warnings?.length || 0);
                                                            return (
                                                                <div className="inline-flex items-center gap-1 px-2.5 py-1 bg-white border border-gray-200 rounded-md font-medium text-gray-600 shadow-xs">
                                                                    <span className="text-gray-400">Warnings:</span>
                                                                    <span className="font-bold text-gray-700">{warnCount}</span>
                                                                </div>
                                                            );
                                                        })()}

                                                        {hldDesign?.coverage?.uncovered_items?.length > 0 ? (
                                                            <div className="inline-flex items-center gap-1 px-2.5 py-1 bg-amber-50 border border-amber-300 rounded-md font-medium text-amber-800 shadow-xs" title={hldDesign.coverage.uncovered_items.map(u => `${u.id}: ${u.requirement}`).join('\n')}>
                                                                <span>Uncovered Requirements:</span>
                                                                <span className="font-bold">{hldDesign.coverage.uncovered_items.length}</span>
                                                            </div>
                                                        ) : hldDesign?.coverage ? (
                                                            <div className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] text-emerald-600 font-medium">
                                                                <span>All Requirements Covered</span>
                                                            </div>
                                                        ) : null}

                                                        {hldDesign?.generation_source && (
                                                            <div className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono uppercase bg-slate-100 text-slate-600 border border-slate-200">
                                                                <span>Source: {hldDesign.generation_source}</span>
                                                            </div>
                                                        )}
                                                    </div>
                                                )}

                                                {/* HLD Content */}
                                                {hldDesign?.markdown ? (
                                                    <div className="prose prose-lg prose-slate max-w-none text-app-text-label leading-relaxed">
                                                        <ReactMarkdown
                                                            remarkPlugins={[remarkGfm]}
                                                            components={markdownComponents}
                                                        >
                                                            {sanitizeDesignMarkdownDate(hldDesign.markdown)}
                                                        </ReactMarkdown>
                                                    </div>
                                                ) : (designGenerating || specStatus?.hld === 'generating' || (designLoading && !hldDesign)) ? (
                                                    <div className="py-20 flex flex-col items-center justify-center space-y-3">
                                                        <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
                                                        <p className="text-sm font-semibold text-gray-700">Synthesizing High-Level Design...</p>
                                                        <p className="text-xs text-gray-400">Compiling container topologies, sequence workflows, and security matrices</p>
                                                    </div>
                                                ) : (
                                                    <div className="py-16 flex flex-col items-center justify-center space-y-4 text-center">
                                                        <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center ring-8 ring-blue-50/50">
                                                            <Layers className="w-6 h-6 text-blue-600" />
                                                        </div>
                                                        <h4 className="text-base font-bold text-gray-900">High-Level Design (HLD) Ready for Synthesis</h4>
                                                        <p className="text-xs text-gray-500 max-w-md">
                                                            Synthesize C4 system context, container topology, sequence workflows, and security matrix from your BRD requirements.
                                                        </p>
                                                        <button
                                                            onClick={() => handleRegenerateArchitectureDesign('hld')}
                                                            disabled={designGenerating}
                                                            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-xs font-semibold rounded-lg hover:bg-blue-700 transition-all shadow-sm disabled:opacity-50 cursor-pointer"
                                                        >
                                                            <Sparkles className="w-3.5 h-3.5" />
                                                            <span>Generate High-Level Design (HLD)</span>
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {/* ── VIEW 3: LOW-LEVEL DESIGN (LLD) ── */}
                                        {activeDesignTab === 'lld' && (
                                            <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4 sm:p-6 space-y-6">
                                                {/* Simple Header Bar */}
                                                <div className="pb-4 border-b border-gray-200/80">
                                                    <h2 className="text-xl font-extrabold text-gray-900">
                                                        {lldDesign?.title || `Low-Level Design Specification`}
                                                    </h2>
                                                    <p className="text-xs text-gray-500 mt-0.5">
                                                        Layered module contracts, ER diagram, database dictionary, SQL migration DDL, state machines, and file tree.
                                                    </p>
                                                </div>

                                                {/* Architecture Validation & Traceability Indicators (LLD View) */}
                                                {(lldDesign?.validation || lldDesign?.consistency || lldDesign?.traceability) && (
                                                    <div className="flex flex-wrap items-center gap-2 p-3 bg-gradient-to-r from-indigo-50/70 via-purple-50/50 to-slate-50/70 border border-indigo-100 rounded-lg text-xs">
                                                        {lldDesign?.validation && (
                                                            <div className={`inline-flex items-center gap-1 px-2.5 py-1 bg-white border rounded-md font-semibold shadow-xs ${
                                                                lldDesign.validation.status === 'PASS' ? 'border-emerald-200 text-emerald-700' : 'border-amber-200 text-amber-700'
                                                            }`}>
                                                                <span className="text-gray-500 font-normal">LLD Quality:</span>
                                                                <span className="font-bold">{lldDesign.validation.status}</span>
                                                            </div>
                                                        )}

                                                        {lldDesign?.consistency && (
                                                            <div className={`inline-flex items-center gap-1 px-2.5 py-1 bg-white border rounded-md font-semibold shadow-xs ${
                                                                lldDesign.consistency.status === 'PASS' ? 'border-emerald-200 text-emerald-700' : 'border-amber-200 text-amber-700'
                                                            }`}>
                                                                <span className="text-gray-500 font-normal">HLD ↔ LLD:</span>
                                                                <span className="font-bold">{lldDesign.consistency.status}</span>
                                                            </div>
                                                        )}

                                                        {lldDesign?.traceability && (
                                                            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-white border border-indigo-200/80 rounded-md font-semibold text-indigo-800 shadow-xs">
                                                                <span className="text-gray-500 font-normal">Traceability:</span>
                                                                <span className="font-bold text-indigo-700 uppercase">{lldDesign.traceability.status}</span>
                                                                {lldDesign.traceability.total_traced ? (
                                                                    <span className="text-[10px] text-gray-400">({lldDesign.traceability.total_traced} mapped)</span>
                                                                ) : null}
                                                            </div>
                                                        )}

                                                        {lldDesign?.generation_source && (
                                                            <div className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono uppercase bg-slate-100 text-slate-600 border border-slate-200">
                                                                <span>Source: {lldDesign.generation_source}</span>
                                                            </div>
                                                        )}
                                                    </div>
                                                )}

                                                {/* LLD Content */}
                                                {lldDesign?.markdown ? (
                                                    <div className="prose prose-lg prose-slate max-w-none text-app-text-label leading-relaxed">
                                                        <ReactMarkdown
                                                            remarkPlugins={[remarkGfm]}
                                                            components={markdownComponents}
                                                        >
                                                            {sanitizeDesignMarkdownDate(lldDesign.markdown)}
                                                        </ReactMarkdown>
                                                    </div>
                                                ) : (designGenerating || specStatus?.lld === 'generating' || (designLoading && !lldDesign)) ? (
                                                    <div className="py-20 flex flex-col items-center justify-center space-y-3">
                                                        <Loader2 className="w-8 h-8 text-indigo-600 animate-spin" />
                                                        <p className="text-sm font-semibold text-gray-700">Synthesizing Low-Level Design...</p>
                                                        <p className="text-xs text-gray-400">Compiling data models, OpenAPI endpoint schemas, and migration DDL scripts</p>
                                                    </div>
                                                ) : (
                                                    <div className="py-16 flex flex-col items-center justify-center space-y-4 text-center">
                                                        <div className="w-12 h-12 rounded-xl bg-indigo-50 flex items-center justify-center ring-8 ring-indigo-50/50">
                                                            <Database className="w-6 h-6 text-indigo-600" />
                                                        </div>
                                                        <h4 className="text-base font-bold text-gray-900">Low-Level Design (LLD) Ready for Synthesis</h4>
                                                        <p className="text-xs text-gray-500 max-w-md">
                                                            Synthesize layered module contracts, ER diagram, database dictionary, and SQL migration DDL for this solution.
                                                        </p>
                                                        <button
                                                            onClick={() => handleRegenerateArchitectureDesign('lld')}
                                                            disabled={designGenerating}
                                                            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-xs font-semibold rounded-lg hover:bg-indigo-700 transition-all shadow-sm disabled:opacity-50 cursor-pointer"
                                                        >
                                                            <Sparkles className="w-3.5 h-3.5" />
                                                            <span>Generate Low-Level Design (LLD)</span>
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}