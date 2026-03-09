import { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';
import DOMPurify from 'dompurify';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FileText, Download, Server, Users, Activity, Clock, Loader2 } from 'lucide-react';

const parseStoredDocumentAnalysis = (doc) => {
    try {
        return doc?.analysis_result ? JSON.parse(doc.analysis_result) : null;
    } catch {
        return null;
    }
};

const hasCompletedStoredAnalysis = (analysis) => {
    if (!analysis) return false;
    return String(analysis.analysis || '').trim().length > 0;
};

const hasCompletedDocumentAnalysis = (doc) => hasCompletedStoredAnalysis(parseStoredDocumentAnalysis(doc));

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
    projectsLoading = false 
}) {
    const navigate = useNavigate();
    const location = useLocation();
    const token = localStorage.getItem('token');
    
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

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
                if (hasCompletedDocumentAnalysis(latestDocument)) {
                    // Use stored analysis
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

                // If no stored analysis in latestDocument, check other documents
                const allDocuments = selectedProject.documents || [];
                let foundAnalysis = null;
                let foundDoc = null;
                
                // Check all documents for completed analysis
                for (const doc of allDocuments) {
                    const docAnalysis = parseStoredDocumentAnalysis(doc);
                    if (hasCompletedStoredAnalysis(docAnalysis)) {
                        foundAnalysis = docAnalysis;
                        foundDoc = doc;
                        break;
                    }
                }
                
                if (foundAnalysis && foundDoc) {
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
                    setError('Analysis not yet completed. Please wait for the analysis to finish.');
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
        const timelineDisplay = metrics.timeline
            ? `${metrics.timeline} (For Developer Only Mode)`
            : 'TBD';
        const metricItems = [
            { label: 'Deployment', value: metrics.deployment || 'TBD' },
            { label: 'Resources', value: metrics.resources || 'TBD' },
            { label: 'Complexity', value: metrics.complexity || 'TBD' },
            { label: 'Timeline', value: timelineDisplay },
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

        // Section title
        doc.setFontSize(14);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(...brandBlue);
        doc.text('Executive Summary & Agent Analysis', marginLeft, y);
        y += 8;

        for (const line of lines) {
            const trimmed = line.trim();
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
            <div className="h-full flex items-center justify-center bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
                <div className="text-center">
                    <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mx-auto mb-4" />
                    <p className="text-app-text-muted font-semibold">Loading Agent Analysis...</p>
                </div>
            </div>
        );
    }

    if (error) {
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

    const handleDownloadPDF = () => {
        // Navigate to dashboard to use the PDF download functionality there
        navigate('/dashboard');
    };

    return (
        <div className="h-full overflow-y-auto bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
            <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
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
                    </div>
                </div>

                            {/* Key Metrics Row */}
                            {result.analysis && (
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                                    {(() => {
                                        const metrics = result.analysis.metrics || {};
                                        const timelineDisplay = metrics?.timeline
                                            ? `${metrics.timeline} (For Developer Only Mode)`
                                            : 'TBD';
                                        const metricItems = [
                                            { label: 'Deployment', value: metrics?.deployment || 'TBD', icon: Server, color: 'text-app-primary', bg: 'bg-app-primary-light' },
                                            { label: 'Resources', value: metrics?.resources || 'TBD', icon: Users, color: 'text-purple-600', bg: 'bg-purple-50' },
                                            { label: 'Complexity', value: metrics?.complexity || 'TBD', icon: Activity, color: 'text-orange-600', bg: 'bg-orange-50' },
                                            { label: 'Timeline', value: timelineDisplay, icon: Clock, color: 'text-app-status-success', bg: 'bg-app-status-successBg' }
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

                {/* Main Analysis Content */}
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

                            if (!analysisContent.trim()) {
                                return (
                                    <div className="text-sm text-app-text-muted italic">
                                        No analysis content available.
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

                                {/* Right Column: Key Actions / Q&A (4 cols) */}
                                <div className="lg:col-span-4 space-y-6">
                                    <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4 sm:p-5 lg:sticky lg:top-6">
                                        <div className="flex items-center mb-4">
                                            <div className="w-1.5 h-1.5 rounded-full bg-app-status-warning mr-2"></div>
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
                                                className={`w-full mt-4 py-2.5 text-xs font-bold text-app-bg-card rounded-lg shadow-sm transition-all ${processing
                                                    ? 'bg-app-text-light cursor-not-allowed'
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
