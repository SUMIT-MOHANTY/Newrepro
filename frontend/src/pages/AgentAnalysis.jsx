import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';
import DOMPurify from 'dompurify';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FileText, Download, Server, Users, Activity, Clock, Loader2, KeyRound, Plus } from 'lucide-react';
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

// Mermaid Diagram Component
const MermaidDiagram = ({ code }) => {
    const containerRef = useRef(null);
    const [svg, setSvg] = useState('');
    const [error, setError] = useState(null);

    useEffect(() => {
        let cancelled = false;
        const renderDiagram = async () => {
            try {
                const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
                const { svg: renderedSvg } = await mermaid.render(id, code);
                if (!cancelled) {
                    setSvg(renderedSvg);
                    setError(null);
                }
            } catch (err) {
                console.warn('Mermaid render error:', err);
                if (!cancelled) {
                    setError(err.message || 'Failed to render diagram');
                    setSvg('');
                }
            }
        };
        renderDiagram();
        return () => { cancelled = true; };
    }, [code]);

    if (error) {
        return (
            <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm font-mono my-4">
                <code>{code}</code>
            </pre>
        );
    }

    if (!svg) {
        return (
            <div className="flex items-center justify-center py-8 my-4 bg-gray-50 rounded-lg border border-gray-200">
                <Loader2 className="w-5 h-5 text-gray-400 animate-spin mr-2" />
                <span className="text-sm text-gray-500">Rendering diagram...</span>
            </div>
        );
    }

    return (
        <div className="my-6 p-4 bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
            <div
                ref={containerRef}
                className="flex justify-center [&>svg]:max-w-full"
                dangerouslySetInnerHTML={{ __html: svg }}
            />
        </div>
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

const parseAIResponse = (text) => {
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

    if (lastValidFenced) {
        const before = source.slice(0, lastValidFenced.index);
        const after = source.slice(lastValidFenced.index + lastValidFenced.fullMatch.length);
        const report = `${before}${after}`.trim();
        return {
            report,
            questions: lastValidFenced.parsed.questions || [],
            metrics: lastValidFenced.parsed.metrics || null,
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
            metrics: null,
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
                metrics: parsed.metrics || null,
                title: parsed.title || null,
                prerequisites: parsed.prerequisites || [],
                architecture: parsed.architecture || null
            };
        }
    }

    return {
        report: source,
        questions: [],
        metrics: null,
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
    const [aiQuestions, setAiQuestions] = useState([]);
    const [userAnswers, setUserAnswers] = useState({});
    const [userFeedback, setUserFeedback] = useState('');
    const [governanceContext, setGovernanceContext] = useState(null);
    const [repoContext, setRepoContext] = useState(null);
    const [isArchModalOpen, setIsArchModalOpen] = useState(false);
    const [isSidebarOpen, setIsSidebarOpen] = useState(false); // Start closed by default
    const [analysisInProgress, setAnalysisInProgress] = useState(false); // Track if analysis is running

    const selectedProject = projects.find((p) => p.key === selectedProjectKey) || null;
    const hasGovernanceAssessment = Boolean(selectedProject?.governanceResultId || governanceContext?.result_id);

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
                if (fetchHistory) fetchHistory();
            }
        } catch (e) {
            console.error('History save failed', e);
        }
    }, [selectedProjectKey, projects, governanceContext, repoContext, persistHistoryDocument, fetchHistory]);

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
                (progress, message) => {
                    // Update progress in UI
                    setProgress(progress);
                    setProgressMessage(message);
                },
                30000, // Poll every 30 seconds
                120    // Max 60 minutes (120 * 30s = 3600s)
            );
            
            const { report, questions, metrics, title, prerequisites, architecture } = parseAIResponse(data.analysis || '');
            if (questions.length > 0) setAiQuestions(questions);

            const effectiveGovernanceContext = analysisOptions.governanceContext || governanceContext || null;
            const effectiveRepoContext = analysisOptions.repoContext || repoContext || null;
            const finalFilename = title || (initialContext || result)?.filename;

            const finalResult = {
                ...(initialContext || result),
                filename: finalFilename,
                analysis: {
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
                }
            };
            setResult(finalResult);
            setProgress(100);
            setProgressMessage('Analysis complete!');
            await saveToHistory(finalResult, selectedProjectKey, effectiveRepoContext);
        } catch (err) {
            setError(`Analysis Error: ${err.message}`);
            setProgress(0);
            setProgressMessage('');
        }
    }, [governanceContext, repoContext, userAnswers, userFeedback, result, selectedProjectKey, saveToHistory]);

    const streamAnalysis = useCallback(async (
        payload,
        token,
        initialContext = null,
        analysisOptions = {}
    ) => {
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

            setProgress(85);
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

                            const { report, questions, metrics, prerequisites, architecture } = parseAIResponse(aiText);
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

            const { report, questions, metrics, title, prerequisites, architecture } = parseAIResponse(aiText);

            if (!architecture && !analysisOptions.forceArchitectureRetry) {
                setProgress(92);
                setProgressMessage('Finalizing architecture diagram...');
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
            setResult(finalResult);
            setProgress(100);
            setProgressMessage('Analysis complete!');
            setAiQuestions(questions?.length ? questions : []);
            await saveToHistory(finalResult, selectedProjectKey, effectiveRepoContext);
        } catch (err) {
            setError(`Stream Error: ${err.message}`);
        }
    }, [governanceContext, repoContext, userAnswers, userFeedback, result, selectedProjectKey, saveToHistory]);

    const fetchAnalysisRef = useRef(fetchAnalysis);
    const streamAnalysisRef = useRef(streamAnalysis);
    fetchAnalysisRef.current = fetchAnalysis;
    streamAnalysisRef.current = streamAnalysis;

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
            setError(err.message || 'Repository analysis failed.');
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
            setError(err.message || 'Agent Analysis failed.');
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

        const loadAnalysis = async () => {
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

                // Check if analysis is pending - only trigger if user clicked "Proceed to Agent Analysis"
                if (isPendingGovernanceAnalysis(storedAnalysis)) {
                    const shouldStartAnalysis = sessionStorage.getItem('shouldStartAnalysis') === 'true';
                    const analysisStartedKey = `analysis_started_${latestDocument.id}`;
                    const alreadyStarted = sessionStorage.getItem(analysisStartedKey) === 'true';

                    if (alreadyStarted) {
                        console.log('Analysis already started for this document, skipping...');
                        setLoading(false);
                        return;
                    }

                    if (shouldStartAnalysis && hasGovernanceAssessment) {
                        // Mark as started to prevent re-triggering
                        sessionStorage.setItem(analysisStartedKey, 'true');
                        // Clear the flag so it doesn't trigger again on refresh
                        sessionStorage.removeItem('shouldStartAnalysis');
                        await triggerPendingAnalysis(latestDocument, storedAnalysis);
                    } else if (!hasGovernanceAssessment) {
                        setError('Governance assessment required before analysis.');
                        setLoading(false);
                    } else {
                        // Analysis is pending but user hasn't clicked proceed yet - just show pending state
                        setError('');
                        setLoading(false);
                    }
                    return;
                }

                if (hasCompletedDocumentAnalysis(latestDocument)) {
                    // Load questions and answers from stored analysis
                    const questions = storedAnalysis?.questions || [];
                    const savedAnswers = storedAnalysis?.userAnswers || {};
                    const savedFeedback = storedAnalysis?.userFeedback || '';

                    setAiQuestions(questions);
                    setUserAnswers(savedAnswers);
                    setUserFeedback(savedFeedback);

                    setResult({
                        id: latestDocument.id,
                        filename: latestDocument.filename,
                        extraction: {
                            markdown: latestDocument.full_content || '',
                            html: '',
                            num_pages: null,
                        },
                        analysis: storedAnalysis,
                        revisionNumber: selectedProject.documents?.length || 1,
                    });
                    setLoading(false);
                    return;
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

                    setAiQuestions(questions);
                    setUserAnswers(savedAnswers);
                    setUserFeedback(savedFeedback);

                    setResult({
                        id: foundDoc.id,
                        filename: foundDoc.filename,
                        extraction: {
                            markdown: foundDoc.full_content || '',
                            html: '',
                            num_pages: null,
                        },
                        analysis: foundAnalysis,
                        revisionNumber: selectedProject.documents?.length || 1,
                    });
                } else {
                    let hasPendingAnalysis = false;
                    for (const doc of allDocuments) {
                        const docAnalysis = parseStoredDocumentAnalysis(doc);
                        if (isPendingGovernanceAnalysis(docAnalysis)) {
                            hasPendingAnalysis = true;
                            const shouldStartAnalysis = sessionStorage.getItem('shouldStartAnalysis') === 'true';
                            const analysisStartedKey = `analysis_started_${doc.id}`;
                            const alreadyStarted = sessionStorage.getItem(analysisStartedKey) === 'true';

                            if (alreadyStarted) {
                                console.log('Analysis already started for document', doc.id);
                                setLoading(false);
                                return;
                            }

                            if (shouldStartAnalysis && hasGovernanceAssessment) {
                                sessionStorage.setItem(analysisStartedKey, 'true');
                                sessionStorage.removeItem('shouldStartAnalysis');
                                await triggerPendingAnalysis(doc, docAnalysis);
                                break;
                            } else if (!hasGovernanceAssessment) {
                                setError('Governance assessment required before analysis.');
                                setLoading(false);
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
                setError(err.message || 'Failed to load analysis');
            } finally {
                setLoading(false);
            }
        };

        loadAnalysis();
    }, [selectedProjectKey, selectedProject, projectsLoading, token, hasGovernanceAssessment, location.pathname, analysisInProgress]);
    // Removed: repoContext, triggerPendingAnalysis (to prevent unnecessary re-runs)

    const handleRefineAnalysis = async () => {
        let feedbackToSend = userFeedback;

        if (aiQuestions.length > 0) {
            feedbackToSend = aiQuestions.map((q, i) => {
                const ans = userAnswers[i] || 'No answer provided';
                return `Q: ${q}\nA: ${ans}`;
            }).join('\n\n');

            if (userFeedback.trim()) {
                feedbackToSend += `\n\nAdditional Comments:\n${userFeedback}`;
            }
        }

        // Attach existing architecture so the model can refine instead of replacing it
        if (result?.analysis?.architecture) {
            try {
                const archJson = JSON.stringify(result.analysis.architecture, null, 2);
                feedbackToSend += `\n\nCURRENT_ARCHITECTURE_JSON (refine, do not radically change unless business requirements demand it):\n${archJson}`;
            } catch {
                // ignore serialization errors
            }
        }
        if (!result?.extraction?.markdown || !feedbackToSend.trim()) return;

        setProcessing(true);
        setError('');
        setProgress(20);
        setProgressMessage('Submitting feedback and refinements...');

        const token = localStorage.getItem('token');

        // Get AI config from localStorage
        const aiConfigStr = localStorage.getItem('aiConfig');
        let aiConfig = { apiUrl: '', apiKey: '', model: '', stream: false };
        if (aiConfigStr) {
            try {
                aiConfig = JSON.parse(aiConfigStr);
            } catch { }
        }

        const aiPayload = {
            document_content: repoContext
                ? `${result.extraction.markdown}\n\n${repoContext.context}`
                : result.extraction.markdown,
            api_url: aiConfig?.apiUrl || undefined,
            api_key: aiConfig?.apiKey || undefined,
            model: aiConfig?.model || undefined,
            stream: aiConfig?.stream || false,
            user_feedback: feedbackToSend,
            governance_context: governanceContext || undefined
        };

        try {
            if (aiConfig?.stream || false) {
                await streamAnalysisRef.current(aiPayload, token, result, {
                    repoContext: repoContext,
                    governanceContext: governanceContext,
                });
            } else {
                setProgress(70);
                setProgressMessage('Generating refined Agent Action Plan... This may take up to 10 minutes.');
                await fetchAnalysisRef.current(aiPayload, token, result, {
                    repoContext: repoContext,
                    governanceContext: governanceContext,
                });
            }
        } catch (err) {
            setError(err.message || 'Failed to refine analysis');
        } finally {
            setProcessing(false);
        }
    };

    // ── Helper: render a mermaid code string to a PNG data-URL ──
    const renderMermaidToPng = async (mermaidCode) => {
        try {
            const uniqueId = `pdf-mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
            const { svg } = await mermaid.render(uniqueId, mermaidCode);

            return await new Promise((resolve) => {
                // Convert SVG to base64 data URL using FileReader to avoid cross-origin issues
                // This ensures the canvas doesn't get tainted
                const svgBlob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
                const reader = new FileReader();

                reader.onload = () => {
                    const img = new Image();
                    const dataUrl = reader.result;

                    img.onload = () => {
                        try {
                            const scale = 3; // High retina quality for crisp diagrams (increased from 2)
                            const naturalW = img.naturalWidth || 800;
                            const naturalH = img.naturalHeight || 400;

                            // Create canvas with exact dimensions
                            const canvas = document.createElement('canvas');
                            canvas.width = naturalW * scale;
                            canvas.height = naturalH * scale;

                            const ctx = canvas.getContext('2d');
                            if (!ctx) {
                                resolve(null);
                                return;
                            }

                            // Fill with white background
                            ctx.fillStyle = '#ffffff';
                            ctx.fillRect(0, 0, canvas.width, canvas.height);

                            // Enable image smoothing for better quality
                            ctx.imageSmoothingEnabled = true;
                            ctx.imageSmoothingQuality = 'high';

                            // Scale and draw
                            ctx.scale(scale, scale);
                            ctx.drawImage(img, 0, 0, naturalW, naturalH);

                            // Export as PNG data URL with maximum quality
                            const pngDataUrl = canvas.toDataURL('image/png', 1.0);

                            resolve({
                                dataUrl: pngDataUrl,
                                aspectRatio: naturalH / naturalW,
                            });
                        } catch (drawError) {
                            console.warn('Canvas draw error:', drawError);
                            resolve(null);
                        }
                    };

                    img.onerror = () => {
                        console.warn('Image load error');
                        resolve(null);
                    };

                    // Use base64 data URL directly (no cross-origin issues)
                    img.src = dataUrl;
                };

                reader.onerror = () => {
                    console.warn('FileReader error');
                    resolve(null);
                };

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
            { label: 'Timeline ( For Developer Only Mode)', value: metrics.timeline || 'TBD' },
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
            const erRegex = /```(?:erDiagram|er\s*\n[\s\S]*?)```/gi;
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
                            doc.text('[ARCHITECTURE DIAGRAM]', marginLeft + 8, y + 8);
                            doc.setFontSize(8);
                            doc.setFont('helvetica', 'normal');
                            doc.setTextColor(...mutedText);
                            doc.text('Visual architecture diagram available in the web interface', marginLeft + 8, y + 15);
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

    if (!result) {
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
            {/* Fixed Right Sidebar - Outside main container */}
            <div className={`fixed right-0 bg-white border-l border-gray-200 shadow-2xl transition-transform duration-300 z-40 ${
                isSidebarOpen ? 'translate-x-0' : 'translate-x-full'
            } w-[480px] overflow-hidden`} style={{ top: 'var(--sidebar-top, 0px)', height: 'calc(100vh - var(--sidebar-top, 0px))' }} ref={(el) => {
                if (el) {
                    // Calculate the top offset based on header + stepper height
                    const mainContent = el.closest('.flex-1.min-w-0');
                    if (mainContent) {
                        const header = mainContent.querySelector('header');
                        const stepper = header?.nextElementSibling;
                        let topOffset = 0;
                        if (header) topOffset += header.offsetHeight;
                        if (stepper && stepper.querySelector('[class*="RoadmapHeader"]') !== null || (stepper && !stepper.classList.contains('flex-1'))) {
                            topOffset += stepper.offsetHeight;
                        }
                        el.style.setProperty('--sidebar-top', `${topOffset}px`);
                    }
                }
            }}>

                {/* Sidebar Content */}
                <div className="h-full overflow-y-auto p-6 space-y-6 pt-6">
                    <div className="flex justify-between items-center pb-2 border-b border-gray-100">
                        <h2 className="text-base font-bold text-gray-900">Analysis Data</h2>
                        <button
                            onClick={() => setIsSidebarOpen(false)}
                            className="text-xs text-gray-500 hover:text-gray-900 font-semibold flex items-center transition-colors px-2 py-1.5 hover:bg-gray-100 rounded-md"
                        >
                            <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                            </svg>
                            Hide Details
                        </button>
                    </div>
                    {result?.analysis?.architecture && (() => {
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
                            <div className="bg-white rounded-xl border border-gray-200 p-5">
                                <div className="flex items-center justify-between mb-4">
                                    <h3 className="text-base font-bold text-gray-900">
                                        Application Architecture
                                    </h3>
                                    <button
                                        type="button"
                                        onClick={() => setIsArchModalOpen(true)}
                                        className="text-xs font-semibold text-blue-600 hover:text-blue-800 underline"
                                    >
                                        Expand
                                    </button>
                                </div>

                                {(() => {
                                    // Extract mermaid diagram from analysis content
                                    const analysisContent = result.analysis?.analysis || '';
                                    const mermaidMatch = analysisContent.match(/```mermaid\s*([\s\S]*?)```/);
                                    const mermaidCode = mermaidMatch ? mermaidMatch[1].trim() : null;

                                    if (mermaidCode) {
                                        return (
                                            <div className="rounded-lg border border-gray-200 bg-gray-50 overflow-hidden">
                                                <MermaidDiagram code={mermaidCode} />
                                            </div>
                                        );
                                    }

                                    // Fallback to ReactFlow if no mermaid found
                                    if (rfNodes.length > 0) {
                                        return (
                                            <div className="h-80 w-full rounded-lg border border-gray-200 bg-gray-50 overflow-hidden">
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
                                        <p className="text-sm text-gray-500 italic">
                                            Architecture details are not available.
                                        </p>
                                    );
                                })()}
                            </div>
                        );
                    })()}

                    {/* Clarification Needed Section */}
                    <div className="bg-white rounded-xl border border-gray-200 p-5">
                        <div className="flex items-center mb-4">
                            <div className="w-2 h-2 rounded-full bg-orange-500 mr-2"></div>
                            <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wide">
                                Clarification Needed
                            </h3>
                        </div>

                        <p className="text-xs text-gray-600 mb-6 leading-relaxed">
                            The AI identified these ambiguous areas. Providing answers will refine the feasibility score.
                        </p>

                        {(() => {
                            const questions = aiQuestions?.length > 0
                                ? aiQuestions
                                : (result?.analysis?.questions || []);

                            return questions?.length > 0 ? (
                                <div className="space-y-4 max-h-96 overflow-y-auto pr-2">
                                    {questions.map((q, i) => (
                                        <div key={i} className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                                            <p className="text-xs font-medium text-gray-700 mb-2">{q}</p>
                                            <input
                                                type="text"
                                                value={userAnswers[i] || ''}
                                                onChange={e => setUserAnswers(prev => ({ ...prev, [i]: e.target.value }))}
                                                className="w-full px-3 py-2 text-xs border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white"
                                                placeholder="Your answer..."
                                            />
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <p className="text-xs text-gray-500 italic">No clarification questions at this time.</p>
                            );
                        })()}

                        <div className="mt-6 pt-4 border-t border-gray-200">
                            <label className="block text-xs font-medium text-gray-700 mb-2">Additional Context</label>
                            <textarea
                                value={userFeedback}
                                onChange={(e) => setUserFeedback(e.target.value)}
                                placeholder="Any other details..."
                                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 min-h-[80px] text-xs bg-white resize-none"
                            />
                            <button
                                onClick={handleRefineAnalysis}
                                disabled={processing || (!(aiQuestions?.length) && !(userFeedback || '').trim())}
                                className={`w-full mt-4 py-2.5 text-xs font-bold text-white rounded-lg shadow-sm transition-all ${
                                    processing
                                        ? 'bg-gray-400 cursor-not-allowed'
                                        : 'bg-gray-900 hover:bg-gray-800 hover:shadow-md'
                                }`}
                            >
                                {processing ? 'Refining...' : 'Update Analysis'}
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            {/* Main Content Container */}
            <div className={`transition-all duration-300 ${isSidebarOpen ? 'lg:mr-[480px]' : 'mr-0'}`}>
                <div className="max-w-[1100px] mx-auto px-12 py-6 space-y-6">
                {result && (
                    <div className="space-y-6 animate-fade-in-up">
                        {/* Result Header */}
                        <div className="flex flex-col md:flex-row md:items-center justify-between bg-app-bg-card p-4 rounded-xl shadow-sm border border-app-border-light">
                            <div className="flex items-center mb-4 md:mb-0">
                                <div className="p-2 bg-app-status-successBg rounded-lg mr-3">
                                    <FileText className="w-5 h-5 text-app-status-success" />
                                </div>
                                <div>
                                    <h2 className="text-lg font-bold text-app-text-main break-all sm:break-normal">{result.filename}</h2>
                                    <p className="text-xs text-app-text-muted">
                                        {selectedProject ? `${selectedProject.name} • Analysis Completed` : 'Analysis Completed'}
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-center gap-3 flex-wrap md:flex-nowrap">
                                <button
                                    onClick={handleDownloadPDF}
                                    className="text-sm text-app-text-label hover:text-app-text-main font-medium hover:underline flex items-center transition-colors"
                                    title="Download PDF Report"
                                >
                                    <Download className="w-4 h-4 mr-1" /> Download PDF
                                </button>
                                <div className="hidden sm:block h-4 w-px bg-app-border"></div>
                                <button
                                    onClick={handleNewAnalysis}
                                    className="text-sm text-app-primary hover:text-app-primary-dark font-medium hover:underline flex items-center"
                                >
                                    <Plus className="w-4 h-4 mr-1" /> Analyze Another
                                </button>
                                <div className="hidden sm:block h-4 w-px bg-app-border"></div>
                                {!isSidebarOpen && (
                                    <button
                                        onClick={() => setIsSidebarOpen(true)}
                                        className="text-sm text-app-text-label hover:text-app-text-main font-medium hover:underline flex items-center transition-colors"
                                        title="Show Details"
                                    >
                                        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                                        </svg>
                                        Show Details
                                    </button>
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
                            {/* Progress Bar */}
                            {processing && (
                                <div className="space-y-3 animate-pulse">
                                    <div className="flex justify-between items-center text-xs uppercase tracking-wider text-app-text-muted font-semibold">
                                        <span>{progressMessage}</span>
                                        <span>{progress}%</span>
                                    </div>
                                    <div className="w-full bg-app-bg-muted rounded-full h-1.5 overflow-hidden">
                                        <div
                                            className="bg-app-primary h-1.5 rounded-full transition-all duration-500 ease-out shadow-[0_0_10px_rgba(37,99,235,0.5)]"
                                            style={{ width: `${progress}%` }}
                                        ></div>
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
                                            { label: 'Timeline ( For Developer Only Mode)', value: metrics?.timeline || 'TBD', icon: Clock, color: 'text-app-status-success', bg: 'bg-app-status-successBg' }
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
                                                                headerText.includes('data model') ||
                                                                headerText.includes('database schema') ||
                                                                headerText.includes('er diagram') ||
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
                                                                    headerText.includes('data model') ||
                                                                    headerText.includes('schema') ||
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

                                                                // Hide erDiagram code blocks in frontend
                                                                if (codeBlockType === 'erdiagram' || codeBlockType.includes('er')) {
                                                                    // Skip this entire code block
                                                                    while (i < lines.length - 1) {
                                                                        i++;
                                                                        if (lines[i].trim().startsWith('```')) {
                                                                            break;
                                                                        }
                                                                    }
                                                                    inCodeBlock = false;
                                                                    codeBlockType = '';
                                                                    continue;
                                                                }
                                                                
                                                                result.push(line);
                                                            } else {
                                                                // End of code block
                                                                inCodeBlock = false;
                                                                codeBlockType = '';
                                                                result.push(line);
                                                            }
                                                            continue;
                                                        }

                                                        // Skip content inside code blocks we're hiding
                                                        if (inCodeBlock && (codeBlockType === 'erdiagram' || codeBlockType.includes('er'))) {
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
                                                        components={{
                                                            h1: ({node, ...props}) => <h1 className="text-lg font-bold text-gray-900 mt-6 mb-3 pb-2 border-b-2 border-gray-200" {...props} />,
                                                            h2: ({node, ...props}) => <h2 className="text-base font-bold text-gray-900 mt-5 mb-2 pb-1 border-b border-gray-200" {...props} />,
                                                            h3: ({node, ...props}) => <h3 className="text-sm font-semibold text-gray-800 mt-4 mb-2" {...props} />,
                                                            h4: ({node, ...props}) => <h4 className="text-sm font-semibold text-gray-700 mt-3 mb-1" {...props} />,
                                                            p: ({node, ...props}) => <p className="text-sm text-gray-700 leading-relaxed mb-3" {...props} />,
                                                            ul: ({node, ...props}) => <ul className="list-disc list-outside ml-5 space-y-1 mb-3 text-sm text-gray-700" {...props} />,
                                                            ol: ({node, ...props}) => <ol className="list-decimal list-outside ml-5 space-y-1 mb-3 text-sm text-gray-700" {...props} />,
                                                            li: ({node, ...props}) => <li className="leading-relaxed text-sm" {...props} />,
                                                            table: ({node, ...props}) => (
                                                                <div className="overflow-x-auto my-6">
                                                                    <table className="min-w-full divide-y divide-gray-200 border border-gray-200 rounded-lg" {...props} />
                                                                </div>
                                                            ),
                                                            thead: ({node, ...props}) => <thead className="bg-gray-50" {...props} />,
                                                            th: ({node, ...props}) => <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200" {...props} />,
                                                            td: ({node, ...props}) => <td className="px-4 py-3 text-sm text-gray-700 border-t border-gray-200" {...props} />,
                                                            code: ({node, inline, className, children, ...props}) => {
                                                                // Show inline code, show blocks based on config
                                                                if (inline) {
                                                                    return <code className="bg-gray-100 text-red-600 px-1 py-0.5 rounded text-xs font-mono" {...props}>{children}</code>;
                                                                }
                                                                // Check if this is a mermaid or erDiagram block
                                                                const codeContent = String(children || '').trim();
                                                                const isMermaid = codeContent.startsWith('graph') ||
                                                                    codeContent.includes('flowchart') ||
                                                                    codeContent.includes('sequenceDiagram') ||
                                                                    codeContent.includes('classDiagram') ||
                                                                    codeContent.includes('stateDiagram');

                                                                const isErDiagram = codeContent.includes('[') &&
                                                                    (codeContent.includes('||') || codeContent.includes('}o') || codeContent.includes('o{'));

                                                                if (isMermaid) {
                                                                    return <MermaidDiagram code={codeContent} />;
                                                                }

                                                                return <code className="block bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-xs font-mono" {...props}>{children}</code>;
                                                            },
                                                            pre: ({node, children, ...props}) => {
                                                                // Check if pre block contains mermaid
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
                                                            blockquote: ({node, ...props}) => <blockquote className="border-l-4 border-blue-500 pl-4 italic text-gray-600 my-4 bg-blue-50 py-2" {...props} />,
                                                            a: ({node, ...props}) => <a className="text-blue-600 hover:text-blue-800 underline font-medium" {...props} />,
                                                            strong: ({node, ...props}) => <strong className="font-bold text-gray-900" {...props} />,
                                                        }}
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
                                                {result.extraction?.html ? (
                                                    <div className="bg-app-bg-card rounded-lg border border-app-border overflow-hidden">
                                                        <iframe
                                                            srcDoc={result.extraction.html}
                                                            className="w-full h-[420px] sm:h-[520px] lg:h-[600px] border-0"
                                                            title="Processed Content"
                                                            sandbox="allow-same-origin allow-scripts"
                                                        />
                                                    </div>
                                                ) : (
                                                    <div className="bg-app-bg-page rounded-lg p-4 text-xs font-mono text-app-text-label max-h-96 overflow-y-auto whitespace-pre-wrap border border-app-border-light">
                                                        {result.extraction?.markdown || '(No content extracted)'}
                                                    </div>
                                                )}
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
                                    Application Architecture (Expanded)
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