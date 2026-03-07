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

  useEffect(() => {
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
    }, [selectedProjectKey, selectedProject, projectsLoading, token]);

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
            </div>
        </div>
    );
}
