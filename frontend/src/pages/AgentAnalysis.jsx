import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { API_ENDPOINTS, API_BASE_URL } from '../config';
import DOMPurify from 'dompurify';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FileText, Download, Server, Users, Activity, Clock, Loader2, KeyRound, Plus, Circle, CheckCircle2, Info } from 'lucide-react';
import bourntecLogo from '../assets/bourntec_logo.png';
import ReactFlow, { Background, Controls } from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import mermaid from 'mermaid';

// Initialize mermaid with configuration
mermaid.initialize({
    startOnLoad: false,
    theme: 'default',
    securityLevel: 'loose',
    fontFamily: 'inherit',
});

// Improved Mermaid Diagram Component with smooth animation and expand functionality
const MermaidDiagram = ({ code, showDownload = true }) => {
    const containerRef = useRef(null);
    const [svg, setSvg] = useState('');
    const [error, setError] = useState(null);
    const [downloading, setDownloading] = useState(false);
    const [isExpanded, setIsExpanded] = useState(false);
    const [isRendering, setIsRendering] = useState(false);

    useEffect(() => {
        let cancelled = false;
        const renderDiagram = async () => {
            setIsRendering(true);
            try {
                const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
                const { svg: renderedSvg } = await mermaid.render(id, code);
                if (!cancelled) {
                    // Add a small delay for smooth transition effect
                    setTimeout(() => {
                        if (!cancelled) {
                            setSvg(renderedSvg);
                            setError(null);
                            setIsRendering(false);
                        }
                    }, 150);
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

    const handleExpand = () => {
        setIsExpanded(true);
    };

    const handleCloseExpanded = () => {
        setIsExpanded(false);
    };

    if (error) {
        return (
            <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm font-mono my-4">
                <code>{code}</code>
            </pre>
        );
    }

    if (isRendering || !svg) {
        return (
            <div className="flex items-center justify-center py-8 my-4 bg-gray-50 rounded-lg border border-gray-200">
                <div className="flex items-center gap-3">
                    <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                    <span className="text-sm text-gray-500">Rendering diagram...</span>
                </div>
            </div>
        );
    }

    return (
        <>
            {/* Fullscreen Expanded View Modal */}
            {isExpanded && (
                <div
                    className="fixed inset-0 z-[500] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in"
                    onClick={handleCloseExpanded}
                >
                    <div
                        className="relative w-full max-w-5xl max-h-[90vh] bg-white rounded-2xl shadow-2xl overflow-hidden animate-scale-in"
                        onClick={(e) => e.stopPropagation()}
                    >
                        {/* Modal Header */}
                        <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-r from-blue-600 to-blue-700 text-white">
                            <div className="flex items-center gap-3">
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
                                </svg>
                                <span className="font-semibold">Diagram View</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={handleDownloadPNG}
                                    disabled={downloading}
                                    className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium bg-white/20 hover:bg-white/30 disabled:bg-white/10 rounded-lg transition-all"
                                >
                                    <Download className="w-4 h-4" />
                                    {downloading ? 'Saving...' : 'Download PNG'}
                                </button>
                                <button
                                    onClick={handleCloseExpanded}
                                    className="p-2 hover:bg-white/20 rounded-lg transition-all"
                                >
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                    </svg>
                                </button>
                            </div>
                        </div>

                        {/* Expanded Diagram Content */}
                        <div className="p-6 bg-gray-50 overflow-auto max-h-[calc(90vh-60px)]">
                            <div
                                className="flex justify-center"
                                dangerouslySetInnerHTML={{ __html: svg }}
                            />
                        </div>
                    </div>
                </div>
            )}

            {/* Normal View */}
            <div className="my-6 p-4 bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
                {/* Action Buttons */}
                <div className="flex justify-end gap-2 mb-2">
                    {/* Expand Button */}
                    <button
                        onClick={handleExpand}
                        className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold text-gray-700 bg-white hover:bg-gray-50 border border-gray-300 disabled:bg-gray-100 disabled:cursor-not-allowed rounded-lg shadow-sm transition-all hover:shadow-md"
                        title="Expand to fullscreen"
                    >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                        </svg>
                        Expand
                    </button>

                    {/* Download Button */}
                    {showDownload && (
                        <button
                            onClick={handleDownloadPNG}
                            disabled={downloading}
                            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed rounded-lg shadow-sm transition-all"
                            title="Download as PNG"
                        >
                            {downloading ? (
                                <>
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    Downloading...
                                </>
                            ) : (
                                <>
                                    <Download className="w-3.5 h-3.5" />
                                    Download PNG
                                </>
                            )}
                        </button>
                    )}
                </div>

                {/* SVG Diagram with smooth fade-in animation */}
                <div
                    ref={containerRef}
                    className="flex justify-center [&>svg]:max-w-full transition-opacity duration-300 ease-out"
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
    const errorMessage = error?.message || String(error);

    // Check for specific error patterns and provide custom messages
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
            const sectionRegex = /---\s*([A-Z\s&()]+)\s*---\s*([\s\S]*?)(?=---\s*[A-Z\s&()]+\s*---|$)/g;
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
        return <div className="text-xs text-app-text-light">No content available</div>;
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
    const [isArchModalOpen, setIsArchModalOpen] = useState(false);
    const [isSidebarOpen, setIsSidebarOpen] = useState(false); // Start closed by default
    const [sidebarTab, setSidebarTab] = useState('chat'); // 'chat' | 'clarification'
    const [analysisInProgress, setAnalysisInProgress] = useState(false); // Track if analysis is running

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
    const [isChatExpanded, setIsChatExpanded] = useState(false);

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
        if (selectedProjectKey && result) {
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

    // Load governance context from storage
    useEffect(() => {
        const storedContext = sessionStorage.getItem('governanceContext') || localStorage.getItem('governanceContext');
        if (storedContext) {
            try {
                setGovernanceContext(JSON.parse(storedContext));
            } catch { }
        }
    }, []);

    // Load repo context from storage
    useEffect(() => {
        const storedRepoContext = sessionStorage.getItem('repoContext') || localStorage.getItem('repoContext');
        if (storedRepoContext) {
            try {
                const parsed = JSON.parse(storedRepoContext);
                console.log('Loaded repo context from storage:', parsed);
                setRepoContext(parsed);
            } catch (err) {
                console.warn('Failed to parse repo context from storage:', err);
            }
        }
    }, []);

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
            const storedAnalysis = {
                ...(newResult.analysis || {}),
                governanceContext: governanceContext || null,
                repoContextMeta: repoContextMeta || null,
                stages: completedStages || {},  // Include completed stages
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
                        : (data.stages || existingAnalysis.stages || {}),
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

            setResult(finalResult);
            setProgress(100);
            setProgressMessage('Analysis complete!');
            await saveToHistory(finalResult, selectedProjectKey, effectiveRepoContext);
            return finalResult;
        } catch (err) {
            console.error('Analysis error:', err);
            const userFriendlyError = formatAnalysisError(err);
            setError(`Analysis Error: ${userFriendlyError}`);
            setProgress(0);
            setProgressMessage('');
            setCompletedStages({});  // Clear stages on error
            setProcessing(false);  // Stop showing the loader
            setAnalysisInProgress(false);  // Clear the in-progress flag
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
        setProgress(70);
        setProgressMessage('Resuming background Agent Analysis...');
        
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
                        : (data.stages || existingAnalysis.stages || {}),
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

            setResult(finalResult);
            setProgress(100);
            setProgressMessage('Analysis complete!');
            await saveToHistory(finalResult, selectedProjectKey, effectiveRepoContext);
            
            // Clean up localStorage keys
            localStorage.removeItem('active_analysis_job_id');
            localStorage.removeItem('active_analysis_project_key');
        } catch (err) {
            console.error('Resumed analysis polling error:', err);
            const userFriendlyError = formatAnalysisError(err);
            setError(`Analysis Error: ${userFriendlyError}`);
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

            const finalResult = {
                ...(initialContext || result),
                filename: finalFilename,
                analysis: {
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
                    model: payload.model || 'Streaming...'
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

            setResult(finalResult);
            setProgress(100);
            setProgressMessage('Analysis complete!');
            setAiQuestions(questions?.length ? questions : []);
            await saveToHistory(finalResult, selectedProjectKey, effectiveRepoContext);
        } catch (err) {
            const userFriendlyError = formatAnalysisError(err);
            setError(`Stream Error: ${userFriendlyError}`);
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
        setProgress(70);
        setProgressMessage('Analyzing repository structure...');
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
                setProgress(85);
                setProgressMessage('Generating repository Agent Action Plan... This may take up to 10 minutes.');
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
        setProgress(70);
        setProgressMessage('Governance completed. Starting Agent Analysis...');
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

            const aiPayload = {
                document_content: pendingRepoContext?.context
                    ? `${document.full_content}\n\n${pendingRepoContext.context}`
                    : document.full_content,
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
                setProgress(85);
                setProgressMessage('Generating comprehensive Agent Action Plan... This may take up to 10 minutes.');
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
        if (isSwitchingProjects && resultCacheRef.current[selectedProjectKey]) {
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
        }

        const loadAnalysis = async () => {
            const storedJobId = localStorage.getItem('active_analysis_job_id');
            const storedProjectKey = localStorage.getItem('active_analysis_project_key');
            if (storedJobId && storedProjectKey === selectedProjectKey) {
                console.log('Found running analysis job in localStorage, resuming polling:', storedJobId);
                const latestDocument = selectedProject.latestDocument;
                const initialResult = {
                    id: latestDocument?.id,
                    filename: latestDocument?.filename || 'BRD',
                    extraction: {
                        markdown: latestDocument?.full_content || '',
                        html: '',
                        num_pages: null,
                    },
                    analysis: { analysis: '', reasoning: '' },
                    revisionNumber: selectedProject.documents?.length || 1,
                };
                
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

                    const loadedResult = {
                        id: latestDocument.id,
                        filename: latestDocument.filename,
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
                            const hasResult = result && result.analysis;

                            if (!hasResult) {
                                // Don't immediately show error - analysis might be starting
                                // Only show error if we're sure it's not running
                                console.log('Analysis was marked as started, but no result yet - might still be initializing');
                                setLoading(false);
                                // Don't set error here - let the analysis continue
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

                const allDocuments = selectedProject.documents || [];
                let foundAnalysis = null;
                let foundDoc = null;

                for (const doc of allDocuments) {
                    const docAnalysis = parseStoredDocumentAnalysis(doc);
                    if (hasCompletedStoredAnalysis(docAnalysis)) {
                        foundAnalysis = docAnalysis;
                        foundDoc = doc;
                        break;
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

                    const loadedResult = {
                        id: foundDoc.id,
                        filename: foundDoc.filename,
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
            const errMsg = {
                id: `err_${Date.now()}`,
                role: 'assistant',
                content: `Update failed: ${err.message || 'Unknown error'}`,
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
                const errMsg = {
                    id: `err_${Date.now()}`,
                    role: 'assistant',
                    content: `Failed to generate techniques: ${err.message || 'Unknown error'}`,
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
            const errMsg = {
                id: `err_${Date.now()}`,
                role: 'assistant',
                content: `Error: ${err.message || 'Unknown error'}`,
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
            const errMsg = {
                id: `err_${Date.now()}`,
                role: 'assistant',
                content: `Technique application failed: ${err.message || 'Unknown error'}`,
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
            const errMsg = {
                id: `qa_err_${Date.now()}`,
                role: 'assistant',
                content: `Failed to apply answers: ${err.message || 'Unknown error'}`,
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
        h2: ({ node, ...props }) => <h2 className="text-base font-bold text-gray-900 mt-5 mb-2 pb-1 border-b border-gray-200" {...props} />,
        h3: ({ node, ...props }) => <h3 className="text-sm font-semibold text-gray-800 mt-4 mb-2" {...props} />,
        h4: ({ node, ...props }) => <h4 className="text-sm font-semibold text-gray-700 mt-3 mb-1" {...props} />,
        p: ({ node, ...props }) => <p className="text-sm text-gray-700 leading-relaxed mb-3" {...props} />,
        ul: ({ node, ...props }) => <ul className="list-disc list-outside ml-5 space-y-1 mb-3 text-sm text-gray-700" {...props} />,
        ol: ({ node, ...props }) => <ol className="list-decimal list-outside ml-5 space-y-1 mb-3 text-sm text-gray-700" {...props} />,
        li: ({ node, ...props }) => <li className="leading-relaxed text-sm" {...props} />,
        table: ({ node, ...props }) => (
            <div className="overflow-x-auto my-4 w-full border border-gray-200 rounded-lg max-w-full">
                <table className="min-w-max w-full divide-y divide-gray-200 table-auto text-xs" {...props} />
            </div>
        ),
        thead: ({ node, ...props }) => <thead className="bg-gray-50" {...props} />,
        th: ({ node, ...props }) => <th className="px-3 py-2 text-left font-bold text-gray-700 uppercase border-b border-gray-200 min-w-[150px] whitespace-normal leading-snug" {...props} />,
        td: ({ node, ...props }) => <td className="px-3 py-2 text-gray-700 border-t border-gray-200 min-w-[150px] whitespace-normal leading-relaxed" {...props} />,
        code: ({ node, inline, className, children, ...props }) => {
            if (inline) {
                return <code className="bg-gray-100 text-red-600 px-1 py-0.5 rounded text-xs font-mono" {...props}>{children}</code>;
            }
            const codeContent = String(children || '').trim();
            const isMermaid = codeContent.startsWith('graph') ||
                codeContent.includes('flowchart') ||
                codeContent.includes('sequenceDiagram') ||
                codeContent.includes('classDiagram') ||
                codeContent.includes('stateDiagram');

            const isErDiagram = codeContent.startsWith('erDiagram') ||
                (codeContent.toLowerCase().startsWith('erdiagram'));

            if (isMermaid || isErDiagram) {
                return <MermaidDiagram code={codeContent} showDownload={true} />;
            }

            return <code className="block bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-xs font-mono" {...props}>{children}</code>;
        },
        pre: ({ node, children, ...props }) => {
            const preContent = String(children || '');
            const codeMatch = preContent.match(/<code[^>]*>([\s\S]*?)<\/code>/);
            const codeContent = codeMatch ? codeMatch[1] : preContent;

            if (codeContent.includes('graph') ||
                codeContent.includes('flowchart') ||
                codeContent.includes('sequenceDiagram') ||
                codeContent.includes('classDiagram') ||
                codeContent.includes('stateDiagram')) {
                return <MermaidDiagram code={codeContent} />;
            }

            return <pre className="bg-gray-900 rounded-lg my-4" {...props}>{children}</pre>;
        },
        blockquote: ({ node, ...props }) => <blockquote className="border-l-4 border-blue-500 pl-4 italic text-gray-600 my-4 bg-blue-50 py-2" {...props} />,
        a: ({ node, ...props }) => <a className="text-blue-600 hover:text-blue-800 underline font-medium" {...props} />,
        strong: ({ node, ...props }) => <strong className="font-bold text-gray-900" {...props} />,
    }), []);

    // ── Helper: render a mermaid code string to a PNG data-URL ──
    const renderMermaidToPng = async (mermaidCode) => {
        try {
            const uniqueId = `pdf-mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
            const { svg } = await mermaid.render(uniqueId, mermaidCode);

            return await new Promise((resolve) => {
                // Parse SVG and force high-resolution dimensions before rasterizing
                const parser = new DOMParser();
                const svgDoc = parser.parseFromString(svg, 'image/svg+xml');
                const svgEl = svgDoc.querySelector('svg');

                let targetW = 2400; // target width for high-res
                let aspectRatio = 0.5; // default fallback

                if (svgEl) {
                    // Read viewBox to get intrinsic aspect ratio
                    const vb = svgEl.getAttribute('viewBox');
                    if (vb) {
                        const parts = vb.trim().split(/[\s,]+/);
                        if (parts.length === 4) {
                            const vbW = parseFloat(parts[2]);
                            const vbH = parseFloat(parts[3]);
                            if (vbW > 0 && vbH > 0) {
                                aspectRatio = vbH / vbW;
                                // If the diagram is very wide, keep targetW; if very tall, cap aspect ratio
                                if (aspectRatio > 3) aspectRatio = 3;
                            }
                        }
                    } else {
                        // Fallback: read explicit width/height attrs
                        const attrW = parseFloat(svgEl.getAttribute('width') || '0');
                        const attrH = parseFloat(svgEl.getAttribute('height') || '0');
                        if (attrW > 0 && attrH > 0) {
                            aspectRatio = attrH / attrW;
                        }
                    }
                    // Force explicit pixel dimensions so the browser renders at full resolution
                    const targetH = Math.round(targetW * aspectRatio);
                    svgEl.setAttribute('width', String(targetW));
                    svgEl.setAttribute('height', String(targetH));
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
                            // Render at 2× of the already-large SVG for maximum sharpness
                            const scale = 2;
                            const canvasW = (img.naturalWidth || targetW) * scale;
                            const canvasH = (img.naturalHeight || targetH) * scale;

                            const canvas = document.createElement('canvas');
                            canvas.width = canvasW;
                            canvas.height = canvasH;

                            const ctx = canvas.getContext('2d');
                            if (!ctx) { resolve(null); return; }

                            // White background
                            ctx.fillStyle = '#ffffff';
                            ctx.fillRect(0, 0, canvasW, canvasH);

                            ctx.imageSmoothingEnabled = true;
                            ctx.imageSmoothingQuality = 'high';
                            ctx.scale(scale, scale);
                            ctx.drawImage(img, 0, 0, img.naturalWidth || targetW, img.naturalHeight || targetH);

                            const pngDataUrl = canvas.toDataURL('image/png', 1.0);
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
        const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
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

        // ── Helper: add page with footer ──
        const totalPagesPlaceholder = '{total_pages}';
        const addFooter = (pageNum) => {
            doc.setDrawColor(...brandBlue);
            doc.setLineWidth(0.3);
            doc.line(marginLeft, pageHeight - 15, pageWidth - marginRight, pageHeight - 15);
            doc.setFontSize(7);
            doc.setTextColor(...mutedText);
            doc.text('Confidential — Generated by BRD Analyzer AI', marginLeft, pageHeight - 10);
            doc.text(`Page ${pageNum} of ${totalPagesPlaceholder}`, pageWidth - marginRight, pageHeight - 10, { align: 'right' });
            doc.text(new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }), pageWidth / 2, pageHeight - 10, { align: 'center' });
        };

        const checkPage = (needed = 12) => {
            if (y + needed > pageHeight - 22) {
                addFooter(doc.internal.getNumberOfPages());
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
        const projectLabel = selectedProject?.name || result.filename || 'Project Analysis';
        doc.text(projectLabel, marginLeft, 31);

        doc.setFontSize(8);
        doc.setTextColor(200, 210, 230);
        doc.text(`Generated: ${new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}`, marginLeft, 41);
        doc.text(`${selectedProject?.name ? selectedProject.name + ' • ' : ''}Confidential`, marginLeft, 48);

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
            const valLines = doc.splitTextToSize(String(m.value), cardW - 8);
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

        const rawText = isLikelyHtml(analysisContent) ? stripHtml(analysisContent) : analysisContent;
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
                const imgData = await renderMermaidToPng('erDiagram\n' + code);
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
                            const imgW = contentWidth;
                            // Calculate height based on aspect ratio, but allow more vertical space
                            const maxHeight = pageHeight - 60; // Leave room for margins
                            let imgH = imgW * imgData.aspectRatio;
                            // If image is taller than page, scale it down
                            if (imgH > maxHeight) {
                                imgH = maxHeight;
                            }
                            checkPage(imgH + 10);
                            // light background card
                            doc.setFillColor(...lightBg);
                            doc.roundedRect(marginLeft, y, contentWidth, imgH + 6, 2, 2, 'F');
                            doc.setFillColor(...brandAccent);
                            doc.rect(marginLeft, y, 2, imgH + 6, 'F');
                            doc.addImage(imgData.dataUrl, 'PNG', marginLeft + 4, y + 3, imgW - 8, imgH);
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
                        // ── Embed actual rendered ER Diagram PNG image ──
                        const imgData = erDiagramImages[erDiagramImageIdx++] || null;
                        if (imgData && imgData.dataUrl) {
                            const imgW = contentWidth;
                            // Calculate height based on aspect ratio, allow more vertical space for ER diagrams
                            const maxHeight = pageHeight - 60; // Leave room for margins
                            let imgH = imgW * imgData.aspectRatio;
                            // If image is taller than page, scale it down
                            if (imgH > maxHeight) {
                                imgH = maxHeight;
                            }
                            checkPage(imgH + 10);
                            // light background card
                            doc.setFillColor(...lightBg);
                            doc.roundedRect(marginLeft, y, contentWidth, imgH + 6, 2, 2, 'F');
                            doc.setFillColor(...brandAccent);
                            doc.rect(marginLeft, y, 2, imgH + 6, 'F');
                            doc.addImage(imgData.dataUrl, 'PNG', marginLeft + 4, y + 3, imgW - 8, imgH);
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
            const isTreeLine = /^[│├└─%]/.test(trimmed) || /^[|\\+]--/.test(trimmed);
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
                        if (/^[│├└─%|\\+]/.test(nextTrimmed)) {
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

        // ── Add footer to last page ──
        addFooter(doc.internal.getNumberOfPages());

        // ── Replace total pages placeholder ──
        const totalPages = doc.internal.getNumberOfPages();
        for (let i = 1; i <= totalPages; i++) {
            doc.setPage(i);
            // Search and replace placeholder
            // jsPDF doesn't have native find-replace, so we added footers with the placeholder.
            // Re-draw footers with actual page count:
        }

        // Re-draw all footers with correct total
        for (let i = 1; i <= totalPages; i++) {
            doc.setPage(i);
            // Clear footer area
            doc.setFillColor(...white);
            doc.rect(0, pageHeight - 18, pageWidth, 18, 'F');
            // Draw final footer
            doc.setDrawColor(...brandBlue);
            doc.setLineWidth(0.3);
            doc.line(marginLeft, pageHeight - 15, pageWidth - marginRight, pageHeight - 15);
            doc.setFontSize(7);
            doc.setTextColor(...mutedText);
            doc.text('Confidential — DSuite by Bourntec Solutions', marginLeft, pageHeight - 10);
            doc.text(`Page ${i} of ${totalPages}`, pageWidth - marginRight, pageHeight - 10, { align: 'right' });
            doc.text(new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }), pageWidth / 2, pageHeight - 10, { align: 'center' });
        }

        // ── Save ──
        const fileName = `${(selectedProject?.name || result.filename || 'BRD_Analysis').replace(/[^a-zA-Z0-9_-]/g, '_')}_Report.pdf`;
        doc.save(fileName);
    };

    const handleNewAnalysis = () => {
        navigate('/dashboard');
    };

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">
                <div className="text-center">
                    <Loader2 className="w-8 h-8 text-app-primary animate-spin mx-auto mb-4" />
                    <p className="text-app-text-muted font-semibold">Loading Agent Analysis...</p>
                </div>
            </div>
        );
    }

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

    // Show loading state while analysis is being prepared or is in progress
    if (!result && (loading || processing)) {
        return (
            <div className="h-full flex items-center justify-center bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">
                <div className="text-center max-w-md">
                    <Loader2 className="w-12 h-12 text-app-primary animate-spin mx-auto mb-4" />
                    <p className="text-app-text-main font-semibold mb-2">
                        {progressMessage || 'Preparing analysis...'}
                    </p>
                    {progress > 0 && (
                        <div className="w-full bg-gray-200 rounded-full h-2 mt-4">
                            <div
                                className="bg-app-primary h-2 rounded-full transition-all duration-300"
                                style={{ width: `${progress}%` }}
                            />
                        </div>
                    )}
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

                                    <div className="flex items-end gap-2">
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
                                                className={`w-full px-3 py-2.5 text-xs border rounded-xl focus:ring-2 resize-none placeholder-gray-400 overflow-y-auto min-h-[42px] max-h-[140px] transition-all duration-300 ${
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
                                            className={`flex-shrink-0 p-2.5 text-white rounded-xl transition-all duration-300 shadow-sm ${
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
                                    <div className="flex items-center justify-between mt-2.5 text-[10px] text-gray-400">
                                        <div className="flex items-center gap-2">
                                            <button
                                                onClick={() => setDiscussMode(prev => !prev)}
                                                disabled={chatSending || processing}
                                                title={
                                                    discussMode
                                                        ? 'Discuss mode enabled - Chat without changing BRD'
                                                        : 'Discuss mode disabled - Sending a message will update the BRD'
                                                }
                                                className={`flex items-center gap-1.5 h-6 px-2.5 rounded-full text-[10px] font-bold transition-all border shadow-xs ${
                                                    discussMode
                                                        ? 'bg-blue-50 border-blue-200 text-blue-600'
                                                        : 'bg-gray-50 border-gray-300 text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                                                }`}
                                            >
                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                                                </svg>
                                                <span>Discuss</span>
                                            </button>
                                        </div>
                                        <span>
                                            {discussMode ? 'Conversational mode' : 'Direct update mode'}
                                        </span>
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
                    {result && (
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

                            <div id="analysis-content" className="bg-transparent space-y-6">
                                {/* Stage-Based Progress Loader */}
                                {processing && (
                                    <div className="bg-app-bg-card rounded-xl border border-app-border p-6 space-y-4">
                                        <div className="flex items-center justify-between mb-4">
                                            <h3 className="text-lg font-bold text-app-text-main">Analysis in Progress</h3>
                                        </div>


                                        {/* Overall Progress Bar */}
                                        <div className="mt-4 space-y-2">
                                            <div className="flex justify-between items-center text-xs text-app-text-muted">
                                                <span>{progressMessage}</span>
                                                <span className="font-semibold">{progress}%</span>
                                            </div>
                                            <div className="w-full bg-app-bg-muted rounded-full h-2 overflow-hidden">
                                                <div
                                                    className="bg-gradient-to-r from-app-primary to-app-primary-hover h-2 rounded-full transition-all duration-500 ease-out shadow-[0_0_10px_rgba(37,99,235,0.5)]"
                                                    style={{ width: `${progress}%` }}
                                                ></div>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {error && (
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
                                        <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4">
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
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Architecture Fullscreen Modal */}
            {isArchModalOpen && result?.analysis?.architecture && (() => {
                const arch = result.analysis.architecture || {};
                const nodes = Array.isArray(arch.nodes) ? arch.nodes : [];
                const edges = Array.isArray(arch.edges) ? arch.edges : [];

                const rfNodes = layoutArchitectureGraph(nodes, edges, 'TB');

                const rfEdges = edges.map((edge, idx) => ({
                    id: String(edge.id || `e-${idx}`),
                    source: String(edge.from),
                    target: String(edge.to),
                    label: edge.description || undefined,
                }));

                return (
                    <div className="fixed inset-0 z-[400] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
                        <div className="relative w-full max-w-6xl h-[80vh] rounded-2xl bg-app-bg-card border border-app-border-light shadow-2xl flex flex-col">
                            <div className="flex items-center justify-between px-4 py-3 border-b border-app-border-light">
                                <h2 className="text-sm font-bold text-app-text-main">
                                    User Flow Diagram (Business Process View)
                                </h2>
                                <button
                                    type="button"
                                    onClick={() => setIsArchModalOpen(false)}
                                    className="text-xs font-semibold text-app-text-muted hover:text-app-text-main px-2 py-1 rounded-md"
                                >
                                    Close
                                </button>
                            </div>
                            <div className="flex-1 bg-app-bg-page overflow-auto p-6">
                                {(() => {
                                    // Extract mermaid diagram from analysis content
                                    const analysisContent = result.analysis?.analysis || '';
                                    const mermaidMatch = analysisContent.match(/```mermaid\s*([\s\S]*?)```/);
                                    const mermaidCode = mermaidMatch ? mermaidMatch[1].trim() : null;

                                    if (mermaidCode) {
                                        return <MermaidDiagram code={mermaidCode} />;
                                    }

                                    // Fallback to ReactFlow if no mermaid found
                                    if (rfNodes.length > 0) {
                                        return (
                                            <div className="h-full">
                                                <ReactFlow
                                                    nodes={rfNodes}
                                                    edges={rfEdges}
                                                    fitView
                                                    nodesDraggable={false}
                                                    nodesConnectable={false}
                                                    elementsSelectable={false}
                                                >
                                                    <Background gap={16} size={1} />
                                                    <Controls showInteractive={false} />
                                                </ReactFlow>
                                            </div>
                                        );
                                    }

                                    return (
                                        <div className="h-full flex items-center justify-center text-xs text-app-text-muted">
                                            Architecture details are not available for this analysis.
                                        </div>
                                    );
                                })()}
                            </div>
                        </div>
                    </div>
                );
            })()}
        </div>
    );
}