import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';
import DOMPurify from 'dompurify';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FileText, Download, Server, Users, Activity, Clock, Loader2, KeyRound, Plus } from 'lucide-react';

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

const hasCompletedDocumentAnalysis = (doc) => hasCompletedStoredAnalysis(parseStoredDocumentAnalysis(doc));

const parseAIResponse = (text) => {
    let source = String(text || '').trim();
    source = source.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();
    source = source.replace(/<think>[\s\S]*/gi, '').trim();

    const hasExpectedShape = (obj) => obj && typeof obj === 'object' && !Array.isArray(obj)
        && ('questions' in obj || 'metrics' in obj || 'title' in obj);

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
            prerequisites: lastValidFenced.parsed.prerequisites || []
        };
    }

    if (lastJsonLikeFence) {
        const before = source.slice(0, lastJsonLikeFence.index);
        const after = source.slice(lastJsonLikeFence.index + lastJsonLikeFence.fullMatch.length);
        return { report: `${before}${after}`.trim(), questions: [], metrics: null, title: null, prerequisites: [] };
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
                prerequisites: parsed.prerequisites || []
            };
        }
    }

    return { report: source, questions: [], metrics: null, title: null, prerequisites: [] };
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
        ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'a', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
        ALLOWED_ATTR: ['href', 'target', 'class'],
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

    const selectedProject = projects.find((p) => p.key === selectedProjectKey) || null;
    const hasGovernanceAssessment = Boolean(selectedProject?.governanceResultId || governanceContext?.result_id);

    // Load governance context from storage
    useEffect(() => {
        const storedContext = sessionStorage.getItem('governanceContext') || localStorage.getItem('governanceContext');
        if (storedContext) {
            try {
                setGovernanceContext(JSON.parse(storedContext));
            } catch {}
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
                const errData = await response.json();
                throw new Error(errData.detail || 'Analysis failed');
            }

            const data = await response.json();
            const { report, questions, metrics, title, prerequisites } = parseAIResponse(data.analysis || '');
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
            setError(`Start Error: ${err.message}`);
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
            setProgressMessage('Generating professional analysis report...');

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

                            const { report, questions, metrics, prerequisites } = parseAIResponse(aiText);
                            if (questions.length > 0) setAiQuestions(questions);

                            setResult(prev => ({
                                ...(prev || initialContext),
                                analysis: {
                                    ...(prev?.analysis || {}),
                                    analysis: report,
                                    reasoning: aiReasoning,
                                    model: payload.model || 'Streaming...',
                                    metrics: metrics,
                                    prerequisites: prerequisites
                                }
                            }));
                        }
                    } catch (e) {
                        console.warn('Error parsing stream chunk', e);
                    }
                }
            }

            const { report, questions, metrics, title, prerequisites } = parseAIResponse(aiText);

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

    const triggerPendingAnalysis = useCallback(async (document, pendingAnalysis) => {
        if (!token) {
            setError('You are not logged in. Please login again.');
            setLoading(false);
            return;
        }

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
                } catch {}
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
                setProgressMessage('Generating professional analysis report...');
                await fetchAnalysisRef.current(aiPayload, token, initialResult, {
                    repoContext: pendingRepoContext,
                    governanceContext: effectiveGovernanceContext,
                });
            }
        } catch (err) {
            setError(err.message || 'Agent Analysis failed.');
        } finally {
            setProcessing(false);
        }
    }, [token, governanceContext, selectedProject, fetchAnalysisRef, streamAnalysisRef]);

    useEffect(() => {
        // Don't run if user is on Governance page - analysis should only start from AgentAnalysis page
        const isOnGovernancePage = location.pathname === '/new-project/governance' || location.pathname.startsWith('/new-project/governance');
        if (isOnGovernancePage) {
            setLoading(false);
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
                if (!latestDocument) {
                    setError('No document found for this project. Please upload a document first.');
                    setLoading(false);
                    return;
                }

                const storedAnalysis = parseStoredDocumentAnalysis(latestDocument);
                
                // Check if analysis is pending - only trigger if user clicked "Proceed to Agent Analysis"
                if (isPendingGovernanceAnalysis(storedAnalysis)) {
                    const shouldStartAnalysis = sessionStorage.getItem('shouldStartAnalysis') === 'true';
                    
                    if (shouldStartAnalysis && hasGovernanceAssessment) {
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
                            
                            if (shouldStartAnalysis && hasGovernanceAssessment) {
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
    }, [selectedProjectKey, selectedProject, projectsLoading, token, hasGovernanceAssessment, triggerPendingAnalysis, location.pathname]);

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
            } catch {}
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
                setProgressMessage('Generating refined analysis report...');
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

    const handleDownloadPDF = () => {
        navigate('/dashboard');
    };

    const handleNewAnalysis = () => {
        navigate('/dashboard');
    };

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
                <div className="text-center">
                    <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mx-auto mb-4" />
                    <p className="text-app-text-muted font-semibold">Loading Agent Analysis...</p>
                </div>
            </div>
        );
    }

    if (error && !result) {
        return (
            <div className="h-full flex items-center justify-center bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
                <div className="text-center max-w-md">
                    <p className="text-red-600 font-semibold mb-4">{error}</p>
                    <button
                        onClick={() => navigate('/dashboard')}
                        className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
                    >
                        Go to Dashboard
                    </button>
                </div>
            </div>
        );
    }

    if (!result) {
        return (
            <div className="h-full flex items-center justify-center bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
                <div className="text-center max-w-md">
                    <p className="text-app-text-muted font-semibold mb-4">No analysis found for this project.</p>
                    <button
                        onClick={() => navigate('/dashboard')}
                        className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
                    >
                        Go to Dashboard
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="h-full overflow-y-auto bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
            <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
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
                                <div className="hidden sm:block h-4 w-px bg-gray-300"></div>
                                <button
                                    onClick={handleNewAnalysis}
                                    className="text-sm text-app-primary hover:text-app-primary-dark font-medium hover:underline flex items-center"
                                >
                                    <Plus className="w-4 h-4 mr-1" /> Analyze Another
                                </button>
                            </div>
                        </div>

                        {hasGovernanceAssessment && (
                            <div className="bg-gradient-to-r from-amber-50 to-orange-50 rounded-xl shadow-sm border border-amber-200/60 p-5 flex flex-col sm:flex-row items-center justify-between gap-4">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-amber-400 to-yellow-500 flex items-center justify-center shadow-lg shadow-amber-200">
                                        <KeyRound className="w-5 h-5 text-white" />
                                    </div>
                                    <div>
                                        <h3 className="text-sm font-bold text-amber-900">Prerequisite Classification</h3>
                                        <p className="text-xs text-amber-700">Review AI-identified prerequisites, credentials, and access requirements before task creation.</p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => navigate('/prerequisites')}
                                    className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-bold text-white bg-gradient-to-r from-amber-500 to-orange-500 rounded-lg shadow-lg shadow-amber-500/30 hover:shadow-amber-500/50 hover:-translate-y-0.5 transition-all active:scale-95 flex-shrink-0"
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
                                    <p className="text-sm font-medium text-red-700">{error}</p>
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
                                            { label: 'Timeline', value: metrics?.timeline || 'TBD', icon: Clock, color: 'text-app-status-success', bg: 'bg-app-status-successBg' }
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

                            {/* Main Content Grid */}
                            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                                {/* Left Column: Report (8 cols) */}
                                <div className="lg:col-span-8 space-y-6">
                                    <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4 sm:p-6">
                                        <h3 className="text-base font-bold text-gray-800 mb-4 pb-2 border-b border-app-border-light">
                                            Executive Summary & Agent Analysis
                                        </h3>
                                        <div className="prose prose-sm prose-slate max-w-none text-app-text-label leading-relaxed">
                                            {(() => {
                                                const analysisContent = result.analysis?.analysis || '';
                                                const explicitHtml = result.analysis?.html;
                                                const htmlToRender = explicitHtml || (isLikelyHtml(analysisContent) ? analysisContent : null);

                                                if (htmlToRender) {
                                                    return (
                                                        <div
                                                            className="bg-app-bg-card rounded-lg border border-app-border p-4"
                                                            dangerouslySetInnerHTML={{ __html: sanitizeHtml(htmlToRender) }}
                                                        />
                                                    );
                                                }

                                                if (processing && !analysisContent.trim()) {
                                                    return (
                                                        <div className="text-sm text-app-text-muted italic">
                                                            Generating analysis...
                                                        </div>
                                                    );
                                                }

                                                return (
                                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                        {analysisContent}
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
                                            <div className="mt-4 pt-4 border-t border-gray-50">
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

                                {/* Right Column: Key Actions / Q&A (4 cols) */}
                                <div className="lg:col-span-4 space-y-6">
                                    <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4 sm:p-5 lg:sticky lg:top-6">
                                        <div className="flex items-center mb-4">
                                            <div className="w-1.5 h-1.5 rounded-full bg-amber-500 mr-2"></div>
                                            <h3 className="text-sm font-bold text-app-text-main uppercase tracking-wide">
                                                Clarification Needed
                                            </h3>
                                        </div>

                                        <p className="text-xs text-app-text-muted mb-6 leading-relaxed">
                                            The AI identified these ambiguous areas. Providing answers will refine the feasibility score.
                                        </p>

                                        {(() => {
                                            // Get questions from state or from result analysis
                                            const questions = aiQuestions?.length > 0 
                                                ? aiQuestions 
                                                : (result?.analysis?.questions || []);
                                            
                                            return questions?.length > 0 ? (
                                                <div className="space-y-4 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
                                                    {questions.map((q, i) => (
                                                        <div key={i} className="bg-app-bg-page rounded-lg p-3 border border-app-border-light">
                                                            <p className="text-xs font-medium text-app-text-label mb-2">{q}</p>
                                                            <input
                                                                type="text"
                                                                value={userAnswers[i] || ''}
                                                                onChange={e => setUserAnswers(prev => ({ ...prev, [i]: e.target.value }))}
                                                                className="w-full px-3 py-2 text-xs border border-app-border rounded-md focus:ring-1 focus:ring-app-primary focus:border-app-primary bg-app-bg-card"
                                                                placeholder="Your answer..."
                                                            />
                                                        </div>
                                                    ))}
                                                </div>
                                            ) : (
                                                <p className="text-xs text-app-text-muted italic">No clarification questions at this time.</p>
                                            );
                                        })()}

                                        <div className="mt-6 pt-4 border-t border-app-border-light">
                                            <label className="block text-xs font-medium text-app-text-label mb-2">Additional Context</label>
                                            <textarea
                                                value={userFeedback}
                                                onChange={(e) => setUserFeedback(e.target.value)}
                                                placeholder="Any other details..."
                                                className="w-full p-3 border border-app-border rounded-lg focus:ring-app-primary focus:border-app-primary min-h-[80px] text-xs bg-app-bg-page resize-none"
                                            />
                                            <button
                                                onClick={handleRefineAnalysis}
                                                disabled={processing || (!(aiQuestions?.length) && !(userFeedback || '').trim())}
                                                className={`w-full mt-4 py-2.5 text-xs font-bold text-white rounded-lg shadow-sm transition-all ${processing
                                                    ? 'bg-gray-400 cursor-not-allowed'
                                                    : 'bg-app-text-main hover:bg-app-text-label hover:shadow-md'
                                                    }`}
                                            >
                                                {processing ? 'Refining...' : 'Update Analysis'}
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
