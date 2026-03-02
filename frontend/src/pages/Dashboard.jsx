import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation, useParams } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';
import { clearAuthData } from '../utils/auth';
import DOMPurify from 'dompurify';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Settings, FileText, History, User, LogOut, Plus, Zap, Server, Users, Activity, Clock, Download, Menu, CheckCircle2, KeyRound } from 'lucide-react';
import { jsPDF } from 'jspdf';
import AIConfig from '../components/AIConfig';

// import bourntecLogo from '../assets/bourntec_logo.png';
import StatusDashboard from '../components/StatusDashboard';
import Sidebar from '../components/Sidebar';
import GitHubIntegration from '../components/GitHubIntegration';

const parseAIResponse = (text) => {
    // Strip <think>...</think> blocks that some models (e.g. minimax-m2.5) embed in content
    let source = String(text || '');
    source = source.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();
    // Also handle unclosed <think> tags (model still streaming reasoning)
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

    // 1) Try fenced blocks first: ```json ... ``` or ``` ... ```
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

    // If we got a fenced JSON-like block but parsing failed, still strip it from the report text.
    if (lastJsonLikeFence) {
        const before = source.slice(0, lastJsonLikeFence.index);
        const after = source.slice(lastJsonLikeFence.index + lastJsonLikeFence.fullMatch.length);
        return { report: `${before}${after}`.trim(), questions: [], metrics: null, title: null, prerequisites: [] };
    }

    // 2) Fallback: parse trailing raw JSON object without fences
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

const isLikelyHtml = (content = '') => {
    const htmlTagPattern = /<\/?(?:!doctype|html|head|body|p|div|h[1-6]|ul|ol|li|table|thead|tbody|tr|td|th|strong|em|span|br|hr|blockquote|img|a|section|article|pre|code)\b/i;
    return htmlTagPattern.test(content);
};

const sanitizeHtml = (content = '') => DOMPurify.sanitize(content, { USE_PROFILES: { html: true } });

const normalizeProjectName = (name = '') => String(name || '').trim().toLowerCase();
const ALL_SKIPPED_ANALYZE_BLOCK_MESSAGE = 'Sandbox is not approved. Our IT team will reach out to you soon.';
const isSkipSelectedOption = (label = '') => String(label || '').trim().toLowerCase() === 'skip';
const buildRepoContextMeta = (context) => {
    const rawRepo = String(context?.repo || '').trim();
    if (!rawRepo) return null;

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
        url: `https://github.com/${normalizedRepo}.git`,
    };
};

const parseRepoMetaFromUrl = (value = '') => {
    if (!String(value || '').includes('github.com/')) return null;
    try {
        const urlObj = new URL(String(value).trim());
        const parts = urlObj.pathname.split('/').filter(Boolean);
        if (parts.length < 2) return null;
        const owner = parts[0];
        const repo = parts[1].replace(/\.git$/i, '');
        if (!owner || !repo) return null;
        let branch = null;
        if (parts[2] === 'tree' && parts[3]) {
            branch = parts[3];
        }
        return {
            repo: `${owner}/${repo}`,
            branch,
            fromLink: true,
        };
    } catch {
        return null;
    }
};


const normalizeDimensionScores = (dimensionScores = {}) => ({
    "Business Value & Urgency": dimensionScores["Business Value & Urgency"] ?? dimensionScores.business_value ?? 0,
    "Data Sensitivity": dimensionScores["Data Sensitivity"] ?? dimensionScores.data_sensitivity ?? 0,
    "Integration & Architecture Complexity": dimensionScores["Integration & Architecture Complexity"] ?? dimensionScores.integration_complexity ?? 0,
    "Operational Impact": dimensionScores["Operational Impact"] ?? dimensionScores.operational_impact ?? 0,
    "AI Risk": dimensionScores["AI Risk"] ?? dimensionScores.ai_risk ?? 0,
    "Ownership & Support": dimensionScores["Ownership & Support"] ?? dimensionScores.ownership ?? 0,
});

const fallbackClassificationDescription = (classification) => {
    if (classification === 'SANDBOX') return 'Sandbox Approved - Low governance required';
    if (classification === 'CONTROLLED_SANDBOX') return 'Controlled Sandbox (Fusion) - Standard template required';
    if (classification === 'ENTERPRISE') return 'Enterprise Build - Full IT oversight required';
    return 'Governance classification unavailable';
};

const buildGovernanceContextFromResult = (resultData) => {
    const normalizedDimensionScores = normalizeDimensionScores(resultData?.dimension_scores || {});
    const formattedAnswers = Array.isArray(resultData?.answers)
        ? resultData.answers.map((answer) => ({
            question_id: answer.question_id,
            score: answer.score,
            selected_option: answer.selected_option || '',
        }))
        : [];

    return {
        project_name: resultData?.project_name || '',
        result_id: resultData?.id || null,
        submission_date: resultData?.submission_date,
        classification: resultData?.classification,
        classification_description: resultData?.classification_description || fallbackClassificationDescription(resultData?.classification),
        weighted_score: resultData?.weighted_score,
        recommendation: resultData?.recommendation,
        hard_stops: resultData?.hard_stops || [],
        answers: formattedAnswers,
        dimension_scores: normalizedDimensionScores,
    };
};





const Dashboard = ({
    user: propUser,
    projects: propProjects,
    projectsLoading: propProjectsLoading,
    selectedProjectKey: propSelectedProjectKey,
    setSelectedProjectKey: propSetSelectedProjectKey,
    showSettings: propShowSettings,
    setShowSettings: propSetShowSettings,
    currentView: propCurrentView,
    isNewProjectMode,
    fetchRoadmapData,
    selectedRole,
    setSelectedRole,
}) => {
    const { projectToken } = useParams();
    const [user, setUser] = useState(propUser || null);
    const [aiConfig, setAiConfig] = useState({
        apiUrl: '',
        apiKey: '',
        model: ''
    });
    const [analyzeWithAi] = useState(true);
    const navigate = useNavigate();

    const [streamResponse] = useState(true);

    const [history, setHistory] = useState([]);
    const [governanceHistory, setGovernanceHistory] = useState([]);
    const [internalProjects, setInternalProjects] = useState([]);
    const projects = propProjects || internalProjects;
    const projectsLoading = propProjectsLoading ?? false;
    const setProjects = setInternalProjects;

    const [internalSelectedProjectKey, setInternalSelectedProjectKey] = useState('');
    const selectedProjectKey = propSelectedProjectKey !== undefined ? propSelectedProjectKey : internalSelectedProjectKey;
    const setSelectedProjectKey = propSetSelectedProjectKey || setInternalSelectedProjectKey;

    const [internalShowSettings, setInternalShowSettings] = useState(false);
    const showSettings = propShowSettings !== undefined ? propShowSettings : internalShowSettings;
    const setShowSettings = propSetShowSettings || setInternalShowSettings;

    // -- Per-Project State Management --
    const [projectStates, setProjectStates] = useState({});

    const getProjectState = (key) => {
        const state = projectStates[key] || {
            files: [], textInput: '', activeTab: 'upload', processing: false,
            result: null, error: '', userFeedback: '', aiQuestions: [],
            userAnswers: {}, revisionUnlocked: false, revisionReason: '',
            progress: 0, progressMessage: ''
        };

        const proj = projects.find(p => p.key === key);
        if (proj?.pendingRevisionReason) {
            return {
                ...state,
                revisionUnlocked: true,
                revisionReason: proj.pendingRevisionReason
            };
        }

        return state;
    };

    const setProjectState = (key, updater) => {
        setProjectStates(prev => {
            const current = prev[key] || getProjectState(key);
            const next = typeof updater === 'function' ? { ...current, ...updater(current) } : { ...current, ...updater };

            return { ...prev, [key]: next };
        });
    };

    const activeState = getProjectState(selectedProjectKey);
    const {
        files = [], linkedFiles = [], textInput, activeTab, processing, result, error,
        userFeedback, aiQuestions, userAnswers, revisionUnlocked,
        revisionReason, progress, progressMessage
    } = activeState;

    // Helpers to update active project state from UI components natively 
    const setFiles = (v) => setProjectState(selectedProjectKey, { files: typeof v === 'function' ? v(activeState.files || []) : v });
    const setLinkedFiles = (v) => setProjectState(selectedProjectKey, { linkedFiles: typeof v === 'function' ? v(activeState.linkedFiles || []) : v });
    const setTextInput = (v) => setProjectState(selectedProjectKey, { textInput: typeof v === 'function' ? v(activeState.textInput) : v });
    const setActiveTab = (v) => setProjectState(selectedProjectKey, { activeTab: typeof v === 'function' ? v(activeState.activeTab) : v });
    const setError = (v) => setProjectState(selectedProjectKey, { error: typeof v === 'function' ? v(activeState.error) : v });
    const setUserFeedback = (v) => setProjectState(selectedProjectKey, { userFeedback: typeof v === 'function' ? v(activeState.userFeedback) : v });
    const setUserAnswers = (v) => setProjectState(selectedProjectKey, { userAnswers: typeof v === 'function' ? v(activeState.userAnswers) : v });

    const location = useLocation();

    const currentView = propCurrentView || (location.pathname === '/status' ? 'statusDashboard' : 'main');

    const [githubLinkUrl, setGithubLinkUrl] = useState('');
    const [githubLinkToken, setGithubLinkToken] = useState('');
    const [githubLinkParsing, setGithubLinkParsing] = useState(false);
    const [githubLinkError, setGithubLinkError] = useState('');
    const [isOAuthRepoSelected, setIsOAuthRepoSelected] = useState(false);

    const [governanceContext, setGovernanceContext] = useState(null);
    const [repoContext, setRepoContext] = useState(null);
    const selectedProject = projects.find((project) => project.key === selectedProjectKey) || null;
    const persistRepoContextMetaForProject = useCallback((ctx, projectKey = selectedProjectKey) => {
        const repoMeta = buildRepoContextMeta(ctx);
        if (!repoMeta) return;
        const keyCandidates = [
            projectKey,
            selectedProject?.key,
            selectedProject?.projectToken,
            selectedProject?.governanceResultId != null ? String(selectedProject.governanceResultId) : null,
            governanceContext?.project_token,
            governanceContext?.result_id != null ? String(governanceContext.result_id) : null,
        ]
            .map((value) => String(value || '').trim())
            .filter(Boolean);

        const serialized = JSON.stringify(repoMeta);
        keyCandidates.forEach((key) => {
            const storageKey = `repo_context_meta_${key}`;
            sessionStorage.setItem(storageKey, serialized);
            localStorage.setItem(storageKey, serialized);
        });
    }, [selectedProjectKey, selectedProject, governanceContext]);
    const isAllGovernanceSkippedCase = (() => {
        if (!governanceContext || typeof governanceContext !== 'object') return false;

        const answerList = Array.isArray(governanceContext.answers) ? governanceContext.answers : [];
        const allAnswersSkipped = answerList.length > 0
            && answerList.every((answer) => isSkipSelectedOption(answer?.selected_option));

        const classificationDescription = String(governanceContext.classification_description || '').toLowerCase();
        const hasSkipFollowUpDescription = classificationDescription.includes('our it team will reach out to you');

        return allAnswersSkipped || hasSkipFollowUpDescription;
    })();
    const isEnterpriseProject = String(governanceContext?.classification || selectedProject?.classification || '') === 'ENTERPRISE';
    const isEnterpriseUploadBlocked = isEnterpriseProject && !isAllGovernanceSkippedCase;
    const getEnterpriseUploadBlockMessage = () => {
        const description = String(governanceContext?.classification_description || '').trim();
        if (description) {
            return `${description} BRD upload is disabled for this project.`;
        }
        return 'Selected project is classified as ENTERPRISE. Upload is disabled until governance is updated.';
    };

    const handleLogout = useCallback(() => {
        clearAuthData();
        navigate('/login');
    }, [navigate]);

    // Fetch history
    const fetchHistory = useCallback(async () => {
        try {
            const token = localStorage.getItem('token');
            const res = await fetch(API_ENDPOINTS.HISTORY, {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (res.status === 401) {
                handleLogout();
                return;
            }
            if (res.ok) setHistory(await res.json());
        } catch (e) {
            console.error('History fetch failed', e);
        }
    }, [handleLogout]);

    const fetchGovernanceHistory = useCallback(async () => {
        try {
            const token = localStorage.getItem('token');
            const res = await fetch(API_ENDPOINTS.GOVERNANCE_HISTORY, {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (res.status === 401) {
                handleLogout();
                return;
            }
            if (res.ok) {
                const payload = await res.json();
                setGovernanceHistory(Array.isArray(payload?.submissions) ? payload.submissions : []);
            }
        } catch (e) {
            console.error('Governance history fetch failed', e);
        }
    }, [handleLogout]);

    const persistGovernanceContext = useCallback((context) => {
        if (!context) return;
        const serializedContext = JSON.stringify(context);
        const serializedResult = JSON.stringify({
            id: context.result_id,
            project_name: context.project_name,
            submission_date: context.submission_date,
            classification: context.classification,
            classification_description: context.classification_description,
            weighted_score: context.weighted_score,
            recommendation: context.recommendation,
            hard_stops: context.hard_stops || [],
            dimension_scores: context.dimension_scores || {},
        });
        sessionStorage.setItem('governanceContext', serializedContext);
        sessionStorage.setItem('governanceResult', serializedResult);
        localStorage.setItem('governanceContext', serializedContext);
        localStorage.setItem('governanceResult', serializedResult);
    }, []);

    const extractProjectMetaFromDocument = useCallback((doc) => {
        let parsedAnalysis = null;
        try {
            parsedAnalysis = doc?.analysis_result ? JSON.parse(doc.analysis_result) : null;
        } catch {
            parsedAnalysis = null;
        }

        const governanceMeta = parsedAnalysis?.governanceContext || {};
        const projectMeta = parsedAnalysis?.projectMeta || {};
        const projectName = projectMeta.project_name || governanceMeta.project_name || 'Unassigned Project';
        const governanceResultId = projectMeta.governance_result_id || governanceMeta.result_id || null;
        const revisionReason = projectMeta.revision_reason || null;
        const revisionNumber = projectMeta.revision_number || null;

        return {
            parsedAnalysis,
            projectName,
            governanceResultId,
            revisionReason,
            revisionNumber,
        };
    }, []);

    // Save history
    const saveToHistory = async (newResult, taskKey = selectedProjectKey) => {
        if (!newResult?.filename) return;

        try {
            const token = localStorage.getItem('token');
            const nextRevisionNumber = ((projects.find(p => p.key === taskKey)?.documents?.length) || 0) + 1;
            const repoContextMeta = newResult?.analysis?.repoContextMeta || buildRepoContextMeta(repoContext);
            const storedAnalysis = {
                ...(newResult.analysis || {}),
                governanceContext: governanceContext || null,
                repoContextMeta: repoContextMeta || null,
                projectMeta: {
                    project_name: (projects.find(p => p.key === taskKey)?.name) || governanceContext?.project_name || 'Project',
                    project_token: (projects.find(p => p.key === taskKey)?.projectToken) || taskKey || null,
                    governance_result_id: governanceContext?.result_id || (projects.find(p => p.key === taskKey)?.governanceResultId) || null,
                    revision_number: nextRevisionNumber,
                    revision_reason: revisionReason || null,
                    repo_context: repoContextMeta || null,
                }
            };

            const res = await fetch(API_ENDPOINTS.HISTORY, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`
                },
                body: JSON.stringify({
                    filename: newResult.filename,
                    content_preview: newResult.extraction?.markdown?.substring(0, 200) + '...',
                    full_content: newResult.extraction?.markdown,
                    analysis_result: JSON.stringify(storedAnalysis)
                })
            });

            if (res.status === 401) {
                handleLogout();
                return;
            }

            if (res.ok) {
                const savedDoc = await res.json();
                setProjectState(taskKey, prev => ({ result: { ...prev.result, id: savedDoc.id }, revisionUnlocked: false, revisionReason: '' }));
                fetchHistory(); // refresh sidebar


            }
        } catch (e) {
            console.error('History save failed', e);
        }
    };

    useEffect(() => {
        const token = localStorage.getItem('token');
        if (!token) {
            navigate('/login');
            return;
        }

        // Check if governance is completed and passed
        // First check sessionStorage (from current session), then localStorage (from previous sessions)
        let governanceResult = sessionStorage.getItem('governanceResult');
        let governanceContext = sessionStorage.getItem('governanceContext');

        // If not in sessionStorage, check localStorage
        if (!governanceResult || !governanceContext) {
            governanceResult = localStorage.getItem('governanceResult');
            governanceContext = localStorage.getItem('governanceContext');
        }

        if (governanceResult && governanceContext) {
            try {
                const parsedResult = JSON.parse(governanceResult);
                const parsedContext = JSON.parse(governanceContext);

                if (parsedResult.classification === 'ENTERPRISE') {
                    localStorage.removeItem('governancePassed');
                } else {
                    localStorage.setItem('governancePassed', 'true');
                }

                // Ensure latest governance context is stored in both sessionStorage and localStorage
                localStorage.setItem('governanceResult', governanceResult);
                localStorage.setItem('governanceContext', governanceContext);
                sessionStorage.setItem('governanceResult', governanceResult);
                sessionStorage.setItem('governanceContext', governanceContext);

                // Set governance context state
                setGovernanceContext(parsedContext);
            } catch (err) {
                console.error('Error parsing governance data:', err);
                localStorage.removeItem('governancePassed');
                localStorage.removeItem('governanceResult');
                localStorage.removeItem('governanceContext');
                sessionStorage.removeItem('governanceResult');
                sessionStorage.removeItem('governanceContext');
                setGovernanceContext(null);
            }
        } else {
            setGovernanceContext(null);
        }

        // Fetch current user
        fetch(API_ENDPOINTS.USERS_ME, {
            headers: { 'Authorization': `Bearer ${token}` }
        })
            .then(res => {
                if (!res.ok) throw new Error('Unauthorized');
                return res.json();
            })
            .then(data => setUser(data))
            .catch(() => {
                handleLogout();
            });

        fetchHistory();
        fetchGovernanceHistory();
    }, [navigate, fetchHistory, fetchGovernanceHistory, handleLogout]);

    const loadGovernanceContextForProject = useCallback(async (resultId) => {
        if (!resultId) return;
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(API_ENDPOINTS.GOVERNANCE_RESULT(resultId), {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!response.ok) {
                if (response.status === 401) {
                    handleLogout();
                }
                return;
            }
            const governanceResult = await response.json();
            const context = buildGovernanceContextFromResult(governanceResult);
            setGovernanceContext(context);
            persistGovernanceContext(context);
        } catch (e) {
            console.error('Failed to load governance context for project', e);
        }
    }, [handleLogout, persistGovernanceContext]);

    useEffect(() => {
        const params = new URLSearchParams(location.search);
        const requestedTab = params.get('tab');
        if (requestedTab === 'upload' || requestedTab === 'text') {
            setActiveTab(requestedTab);
        }

        const governanceId = projectToken || params.get('governance');
        if (governanceId) {
            setSelectedProjectKey(String(governanceId));
        }

        const storedGovernance = sessionStorage.getItem('governanceContext');
        if (!storedGovernance) {
            setGovernanceContext(null);
            return;
        }

        try {
            const parsedGovernance = JSON.parse(storedGovernance);
            const storedId = String(parsedGovernance?.project_token || parsedGovernance?.result_id || '');
            if (!governanceId || storedId === String(governanceId)) {
                setGovernanceContext(parsedGovernance);
            } else {
                setGovernanceContext(null);
            }
        } catch (e) {
            console.warn('Failed to parse governance context from sessionStorage', e);
            sessionStorage.removeItem('governanceContext');
            setGovernanceContext(null);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [location.search, projectToken]);

    useEffect(() => {
        const projectMap = new Map();
        const sortedGovernance = [...governanceHistory].sort(
            (a, b) => new Date(b.submission_date || 0).getTime() - new Date(a.submission_date || 0).getTime()
        );

        sortedGovernance.forEach((submission) => {
            const key = submission.project_token || String(submission.id);
            projectMap.set(key, {
                key,
                governanceResultId: submission.id,
                projectToken: submission.project_token,
                name: submission.project_name || `Project #${submission.id}`,
                classification: submission.classification || 'N/A',
                weightedScore: submission.weighted_score ?? null,
                submissionDate: submission.submission_date || null,
                documents: [],
                latestDocument: null,
                latestRevision: 0,
                status: 'ready_for_upload',
                pendingRevisionReason: submission.pending_revision_reason || null,
            });
        });

        const sortedDocuments = [...history].sort(
            (a, b) => new Date(b.upload_date || 0).getTime() - new Date(a.upload_date || 0).getTime()
        );

        sortedDocuments.forEach((doc) => {
            const meta = extractProjectMetaFromDocument(doc);
            // Try matching by project_token first, then by numeric id
            let targetKey = meta.projectToken || null;
            if (!targetKey || !projectMap.has(targetKey)) {
                // Try to find project by numeric governanceResultId
                const matchedById = meta.governanceResultId
                    ? Array.from(projectMap.values()).find(p => p.governanceResultId === meta.governanceResultId)
                    : null;
                if (matchedById) {
                    targetKey = matchedById.key;
                }
            }

            if (!targetKey || !projectMap.has(targetKey)) {
                const matchedByName = Array.from(projectMap.values()).find(
                    (project) => normalizeProjectName(project.name) === normalizeProjectName(meta.projectName)
                );
                if (matchedByName) {
                    targetKey = matchedByName.key;
                }
            }

            if (!targetKey || !projectMap.has(targetKey)) {
                targetKey = meta.projectToken || (meta.governanceResultId ? String(meta.governanceResultId) : `doc-${doc.id}`);
                if (!projectMap.has(targetKey)) {
                    projectMap.set(targetKey, {
                        key: targetKey,
                        governanceResultId: meta.governanceResultId || null,
                        projectToken: meta.projectToken || null,
                        name: meta.projectName,
                        classification: 'N/A',
                        weightedScore: null,
                        submissionDate: null,
                        documents: [],
                        latestDocument: null,
                        latestRevision: 0,
                        status: 'ready_for_upload',
                    });
                }
            }

            const project = projectMap.get(targetKey);
            project.documents.push(doc);
            if (!project.latestDocument) {
                project.latestDocument = doc;
            }
        });

        const builtProjects = Array.from(projectMap.values())
            .map((project) => {
                const docs = [...project.documents].sort(
                    (a, b) => new Date(b.upload_date || 0).getTime() - new Date(a.upload_date || 0).getTime()
                );
                return {
                    ...project,
                    documents: docs,
                    latestDocument: docs[0] || null,
                    latestRevision: docs.length,
                    status: docs.length > 0 ? 'analysis_complete' : 'ready_for_upload',
                };
            })
            .sort((a, b) => {
                const aDate = new Date(a.submissionDate || a.latestDocument?.upload_date || 0).getTime();
                const bDate = new Date(b.submissionDate || b.latestDocument?.upload_date || 0).getTime();
                return bDate - aDate;
            });

        setProjects(builtProjects);
    }, [governanceHistory, history, extractProjectMetaFromDocument]);

    useEffect(() => {
        if (projects.length === 0) {
            setSelectedProjectKey('');
            return;
        }
        // Don't auto-select when the user is creating a new project
        if (isNewProjectMode) return;
        if (selectedProjectKey && projects.some((project) => project.key === selectedProjectKey)) {
            return;
        }

        const preferredByToken = projectToken
            ? projects.find((project) => project.key === projectToken || project.projectToken === projectToken)
            : null;

        const preferredById = governanceContext?.result_id
            ? projects.find((project) => project.governanceResultId === governanceContext.result_id || project.key === String(governanceContext.result_id))
            : null;

        const preferredByName = governanceContext?.project_name
            ? projects.find((project) => normalizeProjectName(project.name) === normalizeProjectName(governanceContext.project_name))
            : null;

        setSelectedProjectKey(preferredByToken?.key || preferredById?.key || preferredByName?.key || projects[0].key);
    }, [projects, selectedProjectKey, governanceContext, isNewProjectMode]);

    useEffect(() => {
        if (!selectedProject?.governanceResultId) return;
        if (String(governanceContext?.result_id || '') === String(selectedProject.governanceResultId)) {
            return;
        }
        loadGovernanceContextForProject(selectedProject.governanceResultId);
    }, [selectedProject, governanceContext, loadGovernanceContextForProject]);


    const loadHistoryItem = (doc, taskKey = selectedProjectKey) => {
        try {
            const { parsedAnalysis, governanceResultId } = extractProjectMetaFromDocument(doc);
            if (!parsedAnalysis) return;
            const normalized = parseAIResponse(parsedAnalysis.analysis || '');
            // Load questions/answers from saved state
            const questions = (parsedAnalysis.questions?.length ? parsedAnalysis.questions : normalized.questions) || [];
            const metrics = parsedAnalysis.metrics || normalized.metrics;
            const normalizedReport = normalized.report || parsedAnalysis.analysis || '';

            // Handle loading old format vs new format
            const loadedQuestions = questions || parsedAnalysis.questions || [];

            const savedAnswers = parsedAnalysis.userAnswers || {};
            const savedFeedback = parsedAnalysis.userFeedback || '';
            const savedGovernance = parsedAnalysis.governanceContext || null;

            setProjectState(taskKey, { aiQuestions: loadedQuestions, userAnswers: savedAnswers, userFeedback: savedFeedback, error: '' });


            if (savedGovernance) {
                setGovernanceContext(savedGovernance);
                persistGovernanceContext(savedGovernance);
                if (savedGovernance.result_id) {
                    setSelectedProjectKey(String(savedGovernance.result_id));
                }
            } else if (governanceResultId) {
                setSelectedProjectKey(String(governanceResultId));
            }

            // Reconstruct result object
            setProjectState(taskKey, {
                result: {
                    id: doc.id,
                    filename: doc.filename,
                    extraction: {
                        markdown: doc.full_content || doc.content_preview || '(Content not available)',
                        num_pages: null
                    },
                    analysis: {
                        ...parsedAnalysis,
                        analysis: normalizedReport,
                        metrics: metrics || parsedAnalysis.metrics
                    }
                }
            });
        } catch (e) {
            console.error("Failed to load history item", e);
            setError("Failed to load history item. Data might be formatted incorrectly.");
        }
    };

    const handleFileChange = (e) => {
        const selectedFiles = Array.from(e.target.files || []);

        const totalSize = selectedFiles.reduce((acc, file) => acc + file.size, 0);
        const MAX_SIZE_MB = 100;

        if (totalSize > MAX_SIZE_MB * 1024 * 1024) {
            setError(`Total file size cannot exceed ${MAX_SIZE_MB}MB.`);
            return;
        }

        setError(''); // Clear error if validation passes
        if (activeTab === 'linked-doc') {
            setLinkedFiles(selectedFiles);
        } else {
            setFiles(selectedFiles);
        }
    };

    const handleTextChange = (e) => {
        setTextInput(e.target.value);
    };

    const handleUpload = async (e) => {
        const taskKey = selectedProjectKey;
        const taskFiles = activeTab === 'linked-doc' ? linkedFiles : files;
        e.preventDefault();

        if (!selectedProject) {
            setError('Select a project from the sidebar before uploading a BRD.');
            return;
        }
        if (!governanceContext) {
            setError('Governance context is missing for the selected project. Please open Governance Assessment.');
            return;
        }
        if (isEnterpriseUploadBlocked) {
            setError(getEnterpriseUploadBlockMessage());
            return;
        }
        if (selectedProject.documents.length > 0 && !revisionUnlocked) {
            setError('This project is locked after its initial analysis. Create a new revision to upload again.');
            return;
        }

        if (activeTab === 'upload' && files.length === 0) {
            setError('Please select at least one file');
            return;
        }
        if (activeTab === 'linked-doc' && linkedFiles.length === 0) {
            setError('Please select at least one linked document');
            return;
        }
        if (activeTab === 'text' && !textInput.trim()) {
            setError('Please enter some text');
            return;
        }

        // Persist repository choice for this project even if user did not click "Fetch Repository".
        if (activeTab === 'github-link') {
            const repoFromInput = parseRepoMetaFromUrl(githubLinkUrl);
            if (repoFromInput) {
                persistRepoContextMetaForProject(repoFromInput, taskKey);
            }
        }

        setProjectState(taskKey, { processing: true, error: '', result: null, aiQuestions: [], userAnswers: {}, userFeedback: '' });






        try {
            const formData = new FormData();
            const token = localStorage.getItem('token');
            let extractedMarkdown = '';
            let extractedHtml = '';
            let filename = '';

            setProjectState(taskKey, { progress: 10, progressMessage: `Uploading ${taskFiles.length > 0 ? taskFiles.length : ''} documents for ${selectedProject.name}...` });


            if (activeTab === 'upload' || activeTab === 'linked-doc') {
                for (let i = 0; i < taskFiles.length; i++) {
                    formData.append('files', taskFiles[i]);
                }

                // Step 1: Upload and Extract Text (Single Request)
                const uploadResponse = await fetch(API_ENDPOINTS.DOCUMENTS_UPLOAD, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    },
                    body: formData
                });

                if (uploadResponse.status === 401) {
                    handleLogout();
                    return;
                }

                if (!uploadResponse.ok) {
                    const errData = await uploadResponse.json();
                    throw new Error(errData.detail || 'Upload failed');
                }

                setProjectState(taskKey, { progress: 40, progressMessage: 'Processing documents...' });

                const uploadData = await uploadResponse.json();

                // Backend now returns combined markdown/html
                extractedMarkdown = uploadData.markdown;
                extractedHtml = uploadData.html;
                filename = uploadData.filename; // e.g., "doc1.pdf, doc2.pdf"

            } else {
                // Text Input Mode
                extractedMarkdown = textInput;
                filename = 'Pasted_Text_' + new Date().toISOString().slice(0, 10);
                setProjectState(taskKey, { progress: 40, progressMessage: 'Processing documents...' });
            }

            if (isAllGovernanceSkippedCase && analyzeWithAi) {
                setProjectState(taskKey, {
                    progress: 100,
                    progressMessage: 'Analysis blocked pending IT approval.',
                    error: ALL_SKIPPED_ANALYZE_BLOCK_MESSAGE
                });
                return;
            }

            // Set initial result
            const initialResult = {
                filename: filename,
                extraction: {
                    markdown: extractedMarkdown,
                    html: extractedHtml,
                    num_pages: activeTab === 'upload' ? null : 1
                },
                analysis: analyzeWithAi ? { analysis: '', reasoning: '' } : null
            };
            setProjectState(taskKey, { result: initialResult });

            // Step 2: Analyze with AI
            if (analyzeWithAi) {
                const aiPayload = {
                    document_content: repoContext
                        ? `${extractedMarkdown}\n\n${repoContext.context}`
                        : extractedMarkdown,
                    api_url: aiConfig?.apiUrl || undefined,
                    api_key: aiConfig?.apiKey || undefined,
                    model: aiConfig?.model || undefined,
                    stream: streamResponse,
                    governance_context: governanceContext || undefined
                };

                if (streamResponse) {
                    setProjectState(taskKey, { progress: 70, progressMessage: 'Initializing AI task...' });

                    await streamAnalysis(aiPayload, token, initialResult, taskKey);
                } else {
                    setProjectState(taskKey, { progress: 70, progressMessage: 'Initializing AI task...' });

                    await fetchAnalysis(aiPayload, token, initialResult, taskKey);
                }
            } else {
                // If not analyzing, just show the uploaded data
                setProjectState(taskKey, prev => ({ result: { ...prev.result, analysis: null } }));
            }

        } catch (err) {
            setProjectState(taskKey, { error: err.message });
        } finally {
            setProjectState(taskKey, { processing: false });
        }
    };

    // NOTE: Keep fetchAnalysis and other functions unchanged, but they are used inside the loop.
    const fetchAnalysis = async (payload, token, initialContext = null, taskKey = selectedProjectKey) => {
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
                handleLogout();
                return;
            }

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Analysis failed');
            }

            const data = await response.json();
            const { report, questions, metrics, title, prerequisites } = parseAIResponse(data.analysis || '');
            if (questions.length > 0) setProjectState(taskKey, { aiQuestions: questions });

            const finalFilename = title || (initialContext || result).filename;

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
                    governanceContext: governanceContext,
                    repoContextMeta: buildRepoContextMeta(repoContext),
                }
            };
            setProjectState(taskKey, { result: finalResult, progress: 100, progressMessage: 'Analysis complete!' });
            await saveToHistory(finalResult, taskKey);
            createProjectFromMetrics(finalResult, metrics);

            // Auto-refresh roadmap stepper after analysis completes
            if (fetchRoadmapData && selectedProjectKey) {
                fetchRoadmapData(selectedProjectKey);
            }
        } catch (err) {
            setProjectState(taskKey, { error: `Start Error: ${err.message}` });
        }
    };

    const createProjectFromMetrics = async (finalResult, metrics) => {
        try {
            const token = localStorage.getItem('token');
            const tokenRes = await fetch(API_ENDPOINTS.TASK_TOKEN, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    client_id: import.meta.env.VITE_TASK_API_CLIENT_ID || "org_1_596a6282",
                    client_secret: import.meta.env.VITE_TASK_API_CLIENT_SECRET || "voxtdGRCbutV0qHfRQD_Ky1yd9HeCpMuOFKxeUnYB0E"
                })
            });

            if (!tokenRes.ok) throw new Error("Failed to fetch task token");

            const tokenData = await tokenRes.json();
            const taskToken = tokenData.access;

            let teamIds = [];
            try {
                const agentsUrl = API_ENDPOINTS.TASK_TOKEN.replace('token/task/', 'agents/');
                const agentsRes = await fetch(agentsUrl, {
                    method: 'GET',
                    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, 'x-task-token': taskToken }
                });
                if (agentsRes.ok) {
                    const agentsData = await agentsRes.json();
                    if (Array.isArray(agentsData) && agentsData.length > 0) {
                        teamIds = agentsData.map(a => a.user_id || a.id).filter(Boolean);
                    } else if (agentsData.results && Array.isArray(agentsData.results)) {
                        teamIds = agentsData.results.map(a => a.user_id || a.id).filter(Boolean);
                    }
                }
            } catch (err) {
                console.error("Failed to fetch team members:", err);
            }

            const timelineStr = metrics?.timeline || "";
            const parseTimelineToDate = (timeline) => {
                const defaultDate = new Date();
                defaultDate.setFullYear(defaultDate.getFullYear() + 1);
                if (!timeline) return defaultDate.toISOString().split('T')[0];

                const lower = String(timeline).toLowerCase();
                const date = new Date();

                const monthsMatch = lower.match(/(?:^|\s)(\d+)(?:\s*-\s*(\d+))?\s*months?/);
                if (monthsMatch) {
                    const maxVal = monthsMatch[2] ? parseInt(monthsMatch[2], 10) : parseInt(monthsMatch[1], 10);
                    date.setMonth(date.getMonth() + maxVal);
                    return date.toISOString().split('T')[0];
                }
                const weeksMatch = lower.match(/(?:^|\s)(\d+)(?:\s*-\s*(\d+))?\s*weeks?/);
                if (weeksMatch) {
                    const maxVal = weeksMatch[2] ? parseInt(weeksMatch[2], 10) : parseInt(weeksMatch[1], 10);
                    date.setDate(date.getDate() + maxVal * 7);
                    return date.toISOString().split('T')[0];
                }
                const daysMatch = lower.match(/(?:^|\s)(\d+)(?:\s*-\s*(\d+))?\s*days?/);
                if (daysMatch) {
                    const maxVal = daysMatch[2] ? parseInt(daysMatch[2], 10) : parseInt(daysMatch[1], 10);
                    date.setDate(date.getDate() + maxVal);
                    return date.toISOString().split('T')[0];
                }
                const yearsMatch = lower.match(/(?:^|\s)(\d+)(?:\s*-\s*(\d+))?\s*years?/);
                if (yearsMatch) {
                    const maxVal = yearsMatch[2] ? parseInt(yearsMatch[2], 10) : parseInt(yearsMatch[1], 10);
                    date.setFullYear(date.getFullYear() + maxVal);
                    return date.toISOString().split('T')[0];
                }
                return defaultDate.toISOString().split('T')[0];
            };

            const projectCreationUrl = `${API_ENDPOINTS.AGENT_PROJECT_INFO.replace('project-info/', 'projects/')}`;
            const projName = selectedProject?.name || governanceContext?.project_name || "New AI Project";
            let pToken = selectedProject?.projectToken || null;
            if (!pToken) {
                const storedResult = localStorage.getItem('governanceResult');
                if (storedResult) {
                    const res = JSON.parse(storedResult);
                    pToken = res.project_token;
                }
            }

            await fetch(projectCreationUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                    'x-task-token': taskToken,
                },
                body: JSON.stringify({
                    name: projName,
                    deadline: parseTimelineToDate(timelineStr),
                    project_wallet: 1000,
                    team: teamIds.length > 0 ? teamIds : [24],
                    project_token: pToken
                }),
            });
        } catch (err) {
            console.error("Project generation error:", err);
        }
    };

    const streamAnalysis = async (payload, token, initialContext = null, taskKey = selectedProjectKey) => {
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
                handleLogout();
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

            setProjectState(taskKey, { progress: 85, progressMessage: 'Generating professional analysis report...' });


            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');

                // Keep the last partial line in the buffer
                buffer = lines.pop() || '';

                for (const line of lines) {
                    const trimmedLine = line.trim();
                    if (!trimmedLine || !trimmedLine.startsWith('data: ')) continue;

                    const dataStr = trimmedLine.slice(6);
                    if (dataStr === '[DONE]') continue;

                    try {
                        const data = JSON.parse(dataStr);
                        // Handle OpenAI-compatible streaming format
                        if (data.choices && data.choices.length > 0) {
                            const delta = data.choices[0].delta || {};

                            // It seems reasoning content comes as "reasoning_content"
                            if (delta.reasoning_content) {
                                aiReasoning += delta.reasoning_content;
                            }

                            if (delta.content) {
                                aiText += delta.content;
                            }

                            // Parse questions dynamically during stream
                            const { report, questions, metrics, prerequisites } = parseAIResponse(aiText);
                            if (questions.length > 0) setProjectState(taskKey, { aiQuestions: questions });

                            // Update UI gracefully
                            setProjectState(taskKey, prev => ({
                                result: {
                                    ...prev.result,
                                    analysis: {
                                        ...(prev.result?.analysis || {}),
                                        analysis: report,
                                        reasoning: aiReasoning,
                                        model: payload.model || 'Streaming...',
                                        metrics: metrics,
                                        prerequisites: prerequisites
                                    }
                                }
                            }));
                        }
                    } catch (e) {
                        console.warn('Error parsing stream chunk', e);
                    }
                }

            }

            // Save history after stream completes
            const { report, questions, metrics, title, prerequisites } = parseAIResponse(aiText);

            const finalFilename = title || (initialContext || result).filename;

            const finalResult = {
                ...(initialContext || result), // Use scope content
                filename: finalFilename,
                analysis: {
                    analysis: report,
                    questions: questions,
                    metrics: metrics,
                    prerequisites: prerequisites,
                    userAnswers: userAnswers,
                    userFeedback: userFeedback,
                    governanceContext: governanceContext,
                    repoContextMeta: buildRepoContextMeta(repoContext),
                    reasoning: aiReasoning,
                    model: payload.model || 'Streaming...'
                }
            };
            setProjectState(taskKey, {
                result: finalResult,
                progress: 100,
                progressMessage: 'Analysis complete!',
                aiQuestions: questions?.length ? questions : []
            });
            await saveToHistory(finalResult, taskKey);
            createProjectFromMetrics(finalResult, metrics);

            // Auto-refresh roadmap stepper after analysis completes
            if (fetchRoadmapData && selectedProjectKey) {
                fetchRoadmapData(selectedProjectKey);
            }
        } catch (err) {
            setProjectState(taskKey, { error: `Stream Error: ${err.message}` });
        }
    };

    const handleRefineAnalysis = async () => {
        const taskKey = selectedProjectKey; const taskResult = result;
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

        setProjectState(taskKey, { processing: true, error: '', result: null, aiQuestions: [], userAnswers: {}, userFeedback: '' });

        setProjectState(taskKey, { progress: 20, progressMessage: 'Submitting feedback and refinements...' });


        const token = localStorage.getItem('token');
        const aiPayload = {
            document_content: repoContext
                ? `${result.extraction.markdown}\n\n${repoContext.context}`
                : result.extraction.markdown,
            api_url: aiConfig?.apiUrl || undefined,
            api_key: aiConfig?.apiKey || undefined,
            model: aiConfig?.model || undefined,
            stream: streamResponse,
            user_feedback: feedbackToSend,
            governance_context: governanceContext || undefined
        };

        try {
            if (streamResponse) {
                await streamAnalysis(aiPayload, token, taskResult, taskKey);
            } else {
                await fetchAnalysis(aiPayload, token, taskResult, taskKey);
            }
        } catch (err) {
            setProjectState(taskKey, { error: err.message });
        } finally {
            setProjectState(taskKey, { processing: false });
        }
    };

    const handleDownloadPDF = () => {
        if (!result) return;

        try {
            const parseHex = (hex) => {
                const normalized = String(hex || '').replace('#', '').trim();
                const full = normalized.length === 3
                    ? normalized.split('').map((char) => char + char).join('')
                    : normalized;
                const intValue = Number.parseInt(full || '000000', 16);
                return [
                    (intValue >> 16) & 255,
                    (intValue >> 8) & 255,
                    intValue & 255
                ];
            };

            const normalizeForPdf = (value = '') => String(value)
                .replace(/```[\s\S]*?```/g, (match) => match.replace(/```/g, '').trim())
                .replace(/<\s*br\s*\/?>/gi, '\n')
                .replace(/<\/\s*(p|div|h[1-6]|section|article|tr)\s*>/gi, '\n')
                .replace(/<\s*li\s*>/gi, '- ')
                .replace(/<\/\s*(li|ul|ol|table|thead|tbody)\s*>/gi, '\n')
                .replace(/<[^>]+>/g, '')
                .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
                .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
                .replace(/^#{1,6}\s*/gm, '')
                .replace(/\*\*(.*?)\*\*/g, '$1')
                .replace(/\*(.*?)\*/g, '$1')
                .replace(/`([^`]+)`/g, '$1')
                .replace(/&nbsp;/gi, ' ')
                .replace(/&amp;/gi, '&')
                .replace(/&lt;/gi, '<')
                .replace(/&gt;/gi, '>')
                .replace(/&quot;/gi, '"')
                .replace(/&#39;/gi, "'")
                .replace(/&#39;/gi, "'")
                .replace(/[\u2018\u2019]/g, "'")
                .replace(/[\u201C\u201D]/g, '"')
                .replace(/[\u2013\u2014]/g, '-')
                .replace(/\u2026/g, '...')
                .replace(/\u2264/g, '<=')
                .replace(/\u2265/g, '>=')
                // eslint-disable-next-line no-control-regex
                .replace(/[^\x00-\x7F]/g, ' ')
                .replace(/\r/g, '')
                .replace(/\n{3,}/g, '\n\n')
                .trim();

            const palette = {
                primary: '#1E3A8A',
                primarySoft: '#E8EEFF',
                border: '#D6E0F5',
                text: '#1F2937',
                muted: '#64748B'
            };

            const analysisText = normalizeForPdf(result.analysis?.analysis || '');
            const questions = result.analysis?.questions?.length ? result.analysis.questions : aiQuestions;
            const answers = result.analysis?.userAnswers || userAnswers;
            const additionalNotes = normalizeForPdf(result.analysis?.userFeedback || userFeedback || '');
            const reasoningText = normalizeForPdf(result.analysis?.reasoning || '');
            const metricSource = result.analysis?.metrics || {};
            const metricItems = [
                { label: 'Deployment', value: metricSource?.deployment || 'TBD' },
                { label: 'Resources', value: metricSource?.resources || 'TBD' },
                { label: 'Complexity', value: metricSource?.complexity || 'TBD' },
                { label: 'Timeline', value: metricSource?.timeline || 'TBD' }
            ];

            const verdictMatch = analysisText.match(/Verdict:\s*\[?\s*(GO|NO-GO|PROCEED WITH CAUTION)\s*\]?/i);
            const verdict = verdictMatch ? verdictMatch[1].toUpperCase() : 'NOT SPECIFIED';
            const verdictStyle = verdict === 'GO'
                ? { fill: '#DCFCE7', border: '#86EFAC', text: '#166534' }
                : verdict === 'NO-GO'
                    ? { fill: '#FEE2E2', border: '#FCA5A5', text: '#B91C1C' }
                    : { fill: '#FEF3C7', border: '#FCD34D', text: '#B45309' };

            // Extract the first two paragraphs which usually correspond to the Executive Summary section
            const pdfParagraphs = analysisText.split(/\n{2,}/);
            let execSummaryText = pdfParagraphs.slice(0, 2).join('\n\n');
            let remainingAnalysisText = pdfParagraphs.slice(2).join('\n\n');

            // Strip the list number from the Executive Summary heading
            execSummaryText = execSummaryText.replace(/^1\.\s*Executive Summary/i, 'Executive Summary');

            // Renumber the remaining sections down by 1 (e.g., "2. Key Requirements" -> "1. Key Requirements")
            remainingAnalysisText = remainingAnalysisText.replace(/^(#*\s*)(\d+)\.\s/gm, (match, prefix, num) => {
                return `${prefix}${parseInt(num) - 1}. `;
            });

            const pdf = new jsPDF('p', 'mm', 'a4');
            const pageWidth = pdf.internal.pageSize.getWidth();
            const pageHeight = pdf.internal.pageSize.getHeight();
            const marginX = 14;
            const bottomMargin = 14;
            const topBandHeight = 22;
            const contentWidth = pageWidth - marginX * 2;
            const generatedAt = new Date().toLocaleString();
            let cursorY = 0;

            const setTextHex = (hex) => {
                const [r, g, b] = parseHex(hex);
                pdf.setTextColor(r, g, b);
            };

            const setFillHex = (hex) => {
                const [r, g, b] = parseHex(hex);
                pdf.setFillColor(r, g, b);
            };

            const setDrawHex = (hex) => {
                const [r, g, b] = parseHex(hex);
                pdf.setDrawColor(r, g, b);
            };

            const drawHeader = () => {
                setFillHex(palette.primary);
                pdf.rect(0, 0, pageWidth, topBandHeight, 'F');

                pdf.setFont('helvetica', 'bold');
                pdf.setFontSize(13);
                pdf.setTextColor(255, 255, 255);
                pdf.text('Analysis Report', marginX, 9);

                pdf.setFont('helvetica', 'normal');
                pdf.setFontSize(8);
                const docLabel = (result.filename || 'Untitled document').slice(0, 72);
                pdf.text(docLabel, marginX, 15);

                const dateLabel = `Generated ${generatedAt}`;
                const dateWidth = pdf.getTextWidth(dateLabel);
                pdf.text(dateLabel, pageWidth - marginX - dateWidth, 15);

                cursorY = topBandHeight + 8;
                setTextHex(palette.text);
            };

            const ensureSpace = (requiredHeight = 8) => {
                if (cursorY + requiredHeight > pageHeight - bottomMargin) {
                    pdf.addPage();
                    drawHeader();
                }
            };

            const addSectionTitle = (title) => {
                ensureSpace(11);
                setFillHex(palette.primarySoft);
                setDrawHex(palette.border);
                pdf.roundedRect(marginX, cursorY, contentWidth, 8, 1.5, 1.5, 'FD');

                setTextHex(palette.primary);
                pdf.setFont('helvetica', 'bold');
                pdf.setFontSize(10.5);
                pdf.text(title, marginX + 3, cursorY + 5.4);

                cursorY += 11;
                pdf.setFont('helvetica', 'normal');
                pdf.setFontSize(10);
                setTextHex(palette.text);
            };

            const addParagraphs = (text, options = {}) => {
                const {
                    fontSize = 10,
                    lineHeight = 4.8,
                    color = palette.text,
                    bold = false
                } = options;

                const blocks = String(text || '')
                    .split(/\n{2,}/)
                    .map((block) => block.trim())
                    .filter(Boolean);

                if (!blocks.length) return;

                pdf.setFont('helvetica', bold ? 'bold' : 'normal');
                pdf.setFontSize(fontSize);
                setTextHex(color);

                blocks.forEach((block, blockIndex) => {
                    const lines = pdf.splitTextToSize(block, contentWidth);
                    lines.forEach((line) => {
                        ensureSpace(lineHeight);
                        // Re-apply properties after ensureSpace in case it created a new page and reset the font
                        pdf.setFont('helvetica', bold ? 'bold' : 'normal');
                        pdf.setFontSize(fontSize);
                        setTextHex(color);

                        pdf.text(line, marginX, cursorY);
                        cursorY += lineHeight;
                    });

                    if (blockIndex < blocks.length - 1) {
                        cursorY += 1.5;
                    }
                });

                pdf.setFont('helvetica', 'normal');
                setTextHex(palette.text);
            };

            const addMetricsGrid = () => {
                addSectionTitle('Key Metrics');

                const cardGap = 4;
                const cardWidth = (contentWidth - cardGap) / 2;
                const cardHeight = 17;
                const rows = Math.ceil(metricItems.length / 2);
                const totalHeight = rows * cardHeight + (rows - 1) * cardGap;
                const cardFills = ['#F8FAFC', '#F0F9FF', '#F9FAFB', '#ECFEFF'];

                ensureSpace(totalHeight + 2);

                metricItems.forEach((item, index) => {
                    const row = Math.floor(index / 2);
                    const col = index % 2;
                    const x = marginX + col * (cardWidth + cardGap);
                    const y = cursorY + row * (cardHeight + cardGap);

                    setFillHex(cardFills[index % cardFills.length]);
                    setDrawHex(palette.border);
                    pdf.roundedRect(x, y, cardWidth, cardHeight, 1.5, 1.5, 'FD');

                    setTextHex(palette.muted);
                    pdf.setFont('helvetica', 'bold');
                    pdf.setFontSize(8);
                    pdf.text(item.label, x + 3, y + 5);

                    setTextHex(palette.text);
                    pdf.setFont('helvetica', 'normal');
                    pdf.setFontSize(9.5);
                    const valueLines = pdf.splitTextToSize(String(item.value || 'TBD'), cardWidth - 6).slice(0, 2);
                    pdf.text(valueLines, x + 3, y + 10);
                });

                cursorY += totalHeight + 2;
            };

            drawHeader();

            ensureSpace(25);
            setFillHex('#F8FAFC');
            setDrawHex(palette.border);
            pdf.roundedRect(marginX, cursorY, contentWidth, 19, 2, 2, 'FD');

            setTextHex(palette.text);
            pdf.setFont('helvetica', 'bold');
            pdf.setFontSize(11);
            pdf.text('Project Overview', marginX + 3, cursorY + 6);

            pdf.setFont('helvetica', 'normal');
            pdf.setFontSize(9);
            setTextHex(palette.muted);
            pdf.text(`Document: ${result.filename || 'Untitled'}`, marginX + 3, cursorY + 12);
            pdf.text(`Generated: ${generatedAt}`, marginX + 3, cursorY + 17);

            cursorY += 24;

            addSectionTitle('Go / No-Go Recommendation');
            ensureSpace(14);
            setFillHex(verdictStyle.fill);
            setDrawHex(verdictStyle.border);
            pdf.roundedRect(marginX, cursorY, contentWidth, 12, 2, 2, 'FD');
            setTextHex(verdictStyle.text);
            pdf.setFont('helvetica', 'bold');
            pdf.setFontSize(11.5);
            pdf.text(verdict, marginX + 3, cursorY + 7.4);
            cursorY += 15;
            cursorY += 4; // Add extra space before Executive Summary

            addParagraphs(execSummaryText || 'Executive summary not available.', {
                fontSize: 10,
                lineHeight: 4.8,
                color: palette.text
            });

            cursorY += 2;
            addMetricsGrid();

            addSectionTitle('Analysis');
            cursorY += 3; // Add extra space below the Analysis heading

            addParagraphs(remainingAnalysisText || analysisText || 'No analysis text available.', {
                fontSize: 10,
                lineHeight: 4.8
            });

            if (questions?.length) {
                cursorY += 2;
                addSectionTitle('Targeted Questions & Clarifications');
                cursorY += 3; // Add extra space below the Clarifications heading

                questions.forEach((question, index) => {
                    const questionText = normalizeForPdf(question);
                    const answerText = normalizeForPdf(answers?.[index] || '');

                    addParagraphs(`${index + 1}. ${questionText}`, {
                        fontSize: 10,
                        lineHeight: 4.8,
                        bold: true
                    });
                    addParagraphs(`Answer: ${answerText || 'Pending clarification'}`, {
                        fontSize: 10,
                        lineHeight: 4.8,
                        color: answerText ? palette.muted : '#94A3B8'
                    });
                    cursorY += 1;
                });
            }

            if (additionalNotes) {
                cursorY += 2;
                addSectionTitle('Additional Context');
                addParagraphs(additionalNotes, {
                    fontSize: 10,
                    lineHeight: 4.8,
                    color: palette.muted
                });
            }

            if (reasoningText) {
                cursorY += 2;
                addSectionTitle('Model Reasoning Notes');
                addParagraphs(reasoningText, {
                    fontSize: 10,
                    lineHeight: 4.8,
                    color: palette.muted
                });
            }

            const totalPages = pdf.getNumberOfPages();
            for (let page = 1; page <= totalPages; page += 1) {
                pdf.setPage(page);
                pdf.setFont('helvetica', 'normal');
                pdf.setFontSize(8);
                setTextHex('#94A3B8');
                const footerLabel = `Page ${page} of ${totalPages}`;
                const footerWidth = pdf.getTextWidth(footerLabel);
                pdf.text(footerLabel, pageWidth - marginX - footerWidth, pageHeight - 6);
            }

            const safeFilename = String(result.filename || 'Report')
                .replace(/[^a-zA-Z0-9._-]/g, '_')
                .slice(0, 80);
            pdf.save(`DSuite_Analysis_${safeFilename}.pdf`);
        } catch (err) {
            console.error('PDF generation failed', err);
            setError(`PDF Error: ${err.message || 'Unknown error'}`);
        }
    };

    const handleLoadGithubUrl = async () => {
        setGithubLinkError('');
        if (!githubLinkUrl.includes('github.com/')) {
            setGithubLinkError('Please enter a valid GitHub URL (e.g. https://github.com/owner/repo)');
            return;
        }

        try {
            const urlObj = new URL(githubLinkUrl);
            const parts = urlObj.pathname.split('/').filter(Boolean);
            if (parts.length < 2) throw new Error('Invalid repo URL structure');

            const owner = parts[0];
            const repo = parts[1].replace(/\.git$/i, '');
            let branch = 'main';
            if (parts[2] === 'tree' && parts[3]) {
                branch = parts[3];
            }
            if (!owner || !repo) {
                throw new Error('Invalid GitHub URL. Use format: https://github.com/owner/repo');
            }

            setGithubLinkParsing(true);
            const token = localStorage.getItem('token');
            const providedPat = githubLinkToken.trim();
            const resp = await fetch(API_ENDPOINTS.GITHUB_REPO_CONTEXT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ owner, repo, branch, token: providedPat || null })
            });
            const data = await resp.json();
            if (!resp.ok) {
                let errMessage = 'Failed to fetch repository';
                if (data.detail) {
                    errMessage = Array.isArray(data.detail) ? data.detail.map(e => e.msg).join(', ') : data.detail;
                }
                throw new Error(errMessage);
            }

            const resolvedRepo = data.repo || `${owner}/${repo}`;
            const resolvedBranch = data.branch || branch;
            const nextRepoContext = {
                repo: resolvedRepo,
                branch: resolvedBranch,
                context: data.context,
                fromLink: true
            };
            setRepoContext(nextRepoContext);
            persistRepoContextMetaForProject(nextRepoContext);
            setGithubLinkError('');
        } catch (e) {
            setGithubLinkError(e.message || 'Failed to parse or load URL');
        } finally {
            setGithubLinkParsing(false);
        }
    };

    const handleNewAnalysis = () => {
        setProjectState(selectedProjectKey, {
            files: [],
            textInput: '',
            processing: false,
            result: null,
            error: '',
            userFeedback: '',
            aiQuestions: [],
            userAnswers: {},
            revisionUnlocked: false,
            revisionReason: '',
            progress: 0,
            progressMessage: ''
        });
    };





    const handleCreateRevision = async () => {
        if (!selectedProject) return;
        const reason = window.prompt(
            `Provide a reason for creating a new revision for "${selectedProject.name}".`
        );
        if (!reason || !reason.trim()) {
            return;
        }

        const trimmedReason = reason.trim();
        const govId = selectedProject.governanceResultId;

        // Save immediately to backend so it persists across logouts
        if (govId) {
            try {
                const token = localStorage.getItem('token');
                if (token) {
                    await fetch(API_ENDPOINTS.GOVERNANCE_REVISION_REASON(govId), {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            Authorization: `Bearer ${token}`
                        },
                        body: JSON.stringify({ reason: trimmedReason })
                    });
                }
            } catch (e) {
                console.error("Failed to save revision reason to backend", e);
            }
        }

        setProjectState(selectedProjectKey, {
            revisionReason: trimmedReason,
            revisionUnlocked: true,
            files: [],
            textInput: '',
            result: null
        });
    };

    const handleViewLatestProjectAnalysis = () => {
        if (!selectedProject?.latestDocument) return;
        loadHistoryItem(selectedProject.latestDocument);
    };

    const goToGovernanceAssessment = () => {
        navigate('/new-project');
    };

    if (!user) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-app-bg-muted">
                <div className="text-app-text-label">Loading...</div>
            </div>
        );
    }

    return (
        <>
            {currentView === 'statusDashboard' ? (
                <div className="h-full overflow-auto">
                    <StatusDashboard
                        projects={projects}
                        projectsLoading={projectsLoading}
                        selectedProjectKey={selectedProjectKey}
                        setSelectedProjectKey={setSelectedProjectKey}
                        selectedRole={selectedRole}
                        setSelectedRole={setSelectedRole}
                    />
                </div>
            ) : (
                <main className="flex-1 h-full overflow-y-auto bg-app-bg-page p-3 sm:p-4 md:p-8 w-full">
                    <div className="max-w-5xl mx-auto space-y-6">

                        {error && (
                            <div className="rounded-lg bg-app-status-errorBg p-4 border border-red-200 flex items-start animate-fade-in-down">
                                <div className="ml-3">
                                    <h3 className="text-sm font-medium text-red-800">Error</h3>
                                    <div className="mt-1 text-sm text-red-700">{error}</div>
                                </div>
                                <button onClick={() => setError('')} className="ml-auto text-app-status-error hover:text-red-700">✕</button>
                            </div>
                        )}



                        {/* Landing / Upload State */}
                        {!result && (
                            <div className="text-center mb-10 animate-fade-in-down">
                                <h1 className="text-3xl font-extrabold text-app-text-main tracking-tight sm:text-4xl mb-3">
                                    AI-Powered BRD Analysis
                                </h1>
                                <p className="text-lg text-app-text-label max-w-2xl mx-auto">
                                    Upload your Business Requirements Document to get instant feasibility analysis, targeted technical questions, and a go/no-go recommendation.
                                </p>
                            </div>
                        )}


                        {!result && (
                            <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4 sm:p-6 md:p-10 transition-shadow hover:shadow-md max-w-3xl mx-auto">
                                <h2 className="text-xl font-bold text-app-text-main mb-6 flex items-center">
                                    <span className="flex items-center justify-center w-8 h-8 rounded-full bg-app-primary-light text-app-primary mr-3 text-sm font-bold">1</span>
                                    Project BRD Upload
                                </h2>

                                <form onSubmit={handleUpload} className="space-y-6">

                                    {selectedProject ? (
                                        <div className="rounded-xl border border-emerald-200 bg-app-status-successBg p-4">
                                            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                                                <div>
                                                    <p className="text-sm font-semibold text-emerald-900">Selected Project</p>
                                                    <p className="text-xs text-emerald-800 mt-1">
                                                        {selectedProject.name} • {selectedProject.classification || 'N/A'} • Score {selectedProject.weightedScore ?? 'N/A'}/10
                                                    </p>
                                                    <p className="text-xs text-emerald-800 mt-1">
                                                        Status: {selectedProject.status === 'analysis_complete' ? 'Analysis Complete (Locked)' : 'Ready for Initial Upload'}
                                                    </p>
                                                    {isEnterpriseUploadBlocked && (
                                                        <p className="text-xs text-red-700 mt-1">
                                                            Upload blocked: {getEnterpriseUploadBlockMessage()}
                                                        </p>
                                                    )}
                                                    {selectedProject.latestDocument && (
                                                        <p className="text-xs text-emerald-800 mt-1">
                                                            Latest document: {selectedProject.latestDocument.filename} ({new Date(selectedProject.latestDocument.upload_date).toLocaleString()})
                                                        </p>
                                                    )}
                                                </div>
                                                <div className="flex flex-col items-start sm:items-end gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={goToGovernanceAssessment}
                                                        className="text-xs font-semibold text-emerald-900 hover:text-emerald-700"
                                                    >
                                                        Change Governance
                                                    </button>
                                                    {selectedProject.latestDocument && (
                                                        <button
                                                            type="button"
                                                            onClick={handleViewLatestProjectAnalysis}
                                                            className="text-xs font-semibold text-emerald-900 hover:text-emerald-700"
                                                        >
                                                            View Latest Analysis
                                                        </button>
                                                    )}
                                                    {selectedProject.documents.length > 0 && !revisionUnlocked && (
                                                        <button
                                                            type="button"
                                                            onClick={handleCreateRevision}
                                                            disabled={isEnterpriseUploadBlocked}
                                                            className="text-xs font-semibold text-app-primary-hover hover:text-blue-900 disabled:text-app-text-light disabled:cursor-not-allowed"
                                                        >
                                                            Create New Revision
                                                        </button>
                                                    )}
                                                </div>
                                            </div>
                                            {revisionUnlocked && (
                                                <div className="mt-3 rounded-lg border border-app-primary-ring bg-app-primary-light p-3">
                                                    <p className="text-xs font-semibold text-blue-900">Revision unlocked for this upload</p>
                                                    <p className="text-xs text-app-primary-dark mt-1">Reason: {revisionReason}</p>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="rounded-xl border border-amber-200 bg-app-status-warningBg p-4">
                                            <p className="text-sm font-semibold text-amber-900">Select a project from the left panel to continue.</p>
                                        </div>
                                    )}

                                    {/* Tabs */}
                                    <div className="flex items-center border-b border-app-border mb-6 overflow-x-auto whitespace-nowrap scrollbar-hide py-1">
                                        <button
                                            type="button"
                                            onClick={() => setActiveTab('upload')}
                                            className={`pb-3 px-3 text-sm font-medium transition-colors relative ${activeTab === 'upload' ? 'text-app-primary border-b-2 border-app-primary' : 'text-app-text-muted hover:text-app-text-label'}`}
                                            disabled={!selectedProject}
                                        >
                                            Upload File
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setActiveTab('linked-doc')}
                                            className={`pb-3 px-3 text-sm font-medium transition-colors relative ${activeTab === 'linked-doc' ? 'text-app-primary border-b-2 border-app-primary' : 'text-app-text-muted hover:text-app-text-label'}`}
                                            disabled={!selectedProject}
                                        >
                                            Linked Project Document
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setActiveTab('text')}
                                            className={`pb-3 px-3 text-sm font-medium transition-colors relative ${activeTab === 'text' ? 'text-app-primary border-b-2 border-app-primary' : 'text-app-text-muted hover:text-app-text-label'}`}
                                            disabled={!selectedProject}
                                        >
                                            Write Text
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setActiveTab('github-link')}
                                            className={`pb-3 px-3 text-sm font-medium transition-colors relative ${activeTab === 'github-link' ? 'text-app-primary border-b-2 border-app-primary' : 'text-app-text-muted hover:text-app-text-label'}`}
                                            disabled={!selectedProject}
                                        >
                                            GitHub
                                        </button>
                                    </div>

                                    {activeTab === 'upload' ? (
                                        <div className={`border-2 border-dashed rounded-xl p-6 sm:p-10 text-center transition-colors bg-app-bg-page/50 group relative ${selectedProject && (selectedProject.documents.length === 0 || revisionUnlocked) && !isEnterpriseUploadBlocked ? 'border-app-border hover:border-blue-400 cursor-pointer' : 'border-app-border opacity-60'}`}>
                                            <input
                                                type="file"
                                                id={`file-upload-${activeTab}`}
                                                multiple
                                                onChange={handleFileChange}
                                                accept=".pdf,.docx,.pptx,.html,.htm,.png,.jpg,.jpeg"
                                                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                                                disabled={!selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked}
                                            />
                                            <div className="mx-auto w-12 h-12 text-app-text-light mb-3 group-hover:text-blue-500 transition-colors">
                                                <FileText className="w-12 h-12" />
                                            </div>
                                            <span className="mt-2 block text-sm font-medium text-app-text-main">
                                                {files.length > 0
                                                    ? `${files.length} file(s) selected`
                                                    : "Click to select documents (max 100MB total)"}
                                            </span>
                                            {files.length > 0 && (
                                                <div className="mt-2 text-xs text-app-text-muted flex flex-col items-center">
                                                    {files.map((f, i) => (
                                                        <span key={i} className="truncate max-w-[200px]">{f.name}</span>
                                                    ))}
                                                </div>
                                            )}
                                            <span className="mt-1 block text-xs text-app-text-light">
                                                PDF, DOCX, PPTX, HTML, Images
                                            </span>
                                        </div>
                                    ) : activeTab === 'linked-doc' ? (
                                        <div className={`border-2 border-dashed rounded-xl p-6 sm:p-10 text-center transition-colors bg-app-bg-page/50 group relative ${selectedProject && (selectedProject.documents.length === 0 || revisionUnlocked) && !isEnterpriseUploadBlocked ? 'border-app-border hover:border-blue-400 cursor-pointer' : 'border-app-border opacity-60'}`}>
                                            <input
                                                type="file"
                                                id={`file-upload-linked`}
                                                multiple
                                                onChange={handleFileChange}
                                                accept=".pdf,.docx,.pptx,.html,.htm,.png,.jpg,.jpeg"
                                                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                                                disabled={!selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked}
                                            />
                                            <div className="mx-auto w-12 h-12 text-app-text-light mb-3 group-hover:text-blue-500 transition-colors">
                                                <FileText className="w-12 h-12" />
                                            </div>
                                            <span className="mt-2 block text-sm font-medium text-app-text-main">
                                                {linkedFiles.length > 0
                                                    ? `${linkedFiles.length} linked document(s) selected`
                                                    : "Click to select linked documents (max 100MB total)"}
                                            </span>
                                            {linkedFiles.length > 0 && (
                                                <div className="mt-2 text-xs text-app-text-muted flex flex-col items-center">
                                                    {linkedFiles.map((f, i) => (
                                                        <span key={i} className="truncate max-w-[200px]">{f.name}</span>
                                                    ))}
                                                </div>
                                            )}
                                            <span className="mt-1 block text-xs text-app-text-light">
                                                PDF, DOCX, PPTX, HTML, Images
                                            </span>
                                        </div>
                                    ) : activeTab === 'text' ? (
                                        <div className="relative">
                                            <textarea
                                                value={textInput}
                                                onChange={handleTextChange}
                                                placeholder="Write your requirements here..."
                                                className="w-full h-64 p-4 border border-app-border rounded-xl focus:ring-2 focus:ring-app-primary focus:border-app-primary text-sm bg-app-bg-page/50 resize-none font-mono"
                                                disabled={!selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked}
                                            />
                                        </div>
                                    ) : (
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 relative mx-auto">
                                            {/* OPTION 1: GitHub Connect */}
                                            <div className="relative border border-app-border rounded-xl p-5 bg-app-bg-card shadow-sm flex flex-col justify-start overflow-hidden">
                                                <div className={`absolute inset-0 bg-app-bg-card/75 backdrop-blur-[2px] z-10 flex items-center justify-center transition-all duration-300 ${((githubLinkUrl && githubLinkUrl.trim().length > 0) || (githubLinkToken && githubLinkToken.trim().length > 0) || (repoContext && repoContext.fromLink)) ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}>
                                                    <span className="text-xs text-app-text-muted font-bold px-3 py-1.5 bg-app-bg-muted rounded-lg shadow-sm border border-app-border uppercase tracking-widest">Using Link Option</span>
                                                </div>
                                                <div className="mb-4">
                                                    <div className="flex items-center mb-2">
                                                        <div className="w-6 h-6 bg-app-primary-light text-app-primary rounded flex items-center justify-center mr-2 font-black text-xs">1</div>
                                                        <h3 className="text-sm font-bold text-app-text-main">Connect Account</h3>
                                                    </div>
                                                    <p className="text-xs text-app-text-muted mb-2">
                                                        Authorize via OAuth to securely browse and select private or public repositories on your account.
                                                    </p>
                                                </div>
                                                <div className="mt-auto">
                                                    <GitHubIntegration
                                                        repoContext={repoContext}
                                                        onRepoSelected={() => setIsOAuthRepoSelected(true)}
                                                        onRepoContextReady={(ctx) => {
                                                            setRepoContext(ctx);
                                                            persistRepoContextMetaForProject(ctx);
                                                            setGithubLinkUrl('');
                                                            setGithubLinkError('');
                                                        }}
                                                        onClearRepo={() => {
                                                            setRepoContext(null);
                                                            setIsOAuthRepoSelected(false);
                                                        }}
                                                    />
                                                </div>
                                            </div>

                                            {/* OPTION 2: Repository URL */}
                                            <div className="relative border border-app-border rounded-xl bg-app-bg-card shadow-sm p-5 flex flex-col justify-start overflow-hidden">
                                                <div className={`absolute inset-0 bg-app-bg-card/75 backdrop-blur-[2px] z-10 flex items-center justify-center transition-all duration-300 ${(isOAuthRepoSelected || (repoContext && !repoContext.fromLink)) ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}>
                                                    <span className="text-xs text-app-text-muted font-bold px-3 py-1.5 bg-app-bg-muted rounded-lg shadow-sm border border-app-border uppercase tracking-widest">Using Connected Account</span>
                                                </div>
                                                <div className="mb-4">
                                                    <div className="flex items-center mb-2">
                                                        <div className="w-6 h-6 bg-purple-100 text-purple-600 rounded flex items-center justify-center mr-2 font-black text-xs">2</div>
                                                        <h3 className="text-sm font-bold text-app-text-main">Paste Repository Link</h3>
                                                    </div>
                                                    <p className="text-xs text-app-text-muted mb-2">
                                                        Provide a direct link to a GitHub repository. For private repositories, include a Personal Access Token (PAT).
                                                    </p>
                                                </div>
                                                <div className="flex flex-col gap-3 mt-auto">
                                                    <input
                                                        type="text"
                                                        value={githubLinkUrl}
                                                        onChange={e => {
                                                            setGithubLinkUrl(e.target.value);
                                                            if (repoContext) setRepoContext(null);
                                                        }}
                                                        placeholder="https://github.com/owner/repo"
                                                        className="w-full px-3 py-2.5 border border-app-border rounded-lg text-sm focus:ring-2 focus:ring-app-primary focus:border-app-primary outline-none transition-all bg-app-bg-page/50"
                                                    />
                                                    <input
                                                        type="password"
                                                        value={githubLinkToken}
                                                        onChange={e => {
                                                            setGithubLinkToken(e.target.value);
                                                            if (repoContext) setRepoContext(null);
                                                        }}
                                                        placeholder="Optional PAT for private repos..."
                                                        className="w-full px-3 py-2.5 border border-app-border rounded-lg text-sm focus:ring-2 focus:ring-app-primary focus:border-app-primary outline-none transition-all bg-app-bg-page/50"
                                                    />
                                                    <div className="flex items-center gap-2">
                                                        <button
                                                            type="button"
                                                            onClick={handleLoadGithubUrl}
                                                            disabled={!githubLinkUrl || githubLinkParsing}
                                                            className="flex-1 px-4 py-2 bg-app-text-main text-white text-sm font-semibold rounded-lg hover:bg-app-text-label disabled:opacity-50 transition-colors inline-flex items-center justify-center h-10 shadow-sm"
                                                        >
                                                            {githubLinkParsing ? (
                                                                <><span className="animate-spin w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full mr-2"></span> Loading...</>
                                                            ) : 'Fetch Repository'}
                                                        </button>
                                                        {repoContext && repoContext.fromLink && (
                                                            <button
                                                                onClick={() => { setRepoContext(null); setGithubLinkUrl(''); setGithubLinkToken(''); setGithubLinkError(''); }}
                                                                className="px-3 py-2 border border-red-200 text-app-status-error bg-app-status-errorBg rounded-lg hover:bg-red-100 text-sm font-semibold h-10 transition-colors"
                                                                title="Clear repository"
                                                            >
                                                                Clear
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>

                                                {githubLinkError && <p className="text-app-status-error text-[11px] font-medium mt-3 bg-app-status-errorBg p-2.5 rounded border border-red-100">{githubLinkError}</p>}
                                                {repoContext && repoContext.fromLink && (
                                                    <div className="mt-3 p-2.5 bg-app-status-successBg border border-emerald-200 rounded text-emerald-800 shadow-sm flex items-center text-xs font-semibold">
                                                        <CheckCircle2 className="w-4 h-4 mr-1.5 flex-shrink-0 text-app-status-success" />
                                                        <span className="truncate">Loaded: {repoContext.repo} {repoContext.branch ? `(${repoContext.branch})` : ''}</span>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )}



                                    {processing && (
                                        <div className="space-y-3 animate-pulse mt-6">
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

                                    <div className="flex justify-end gap-3 pt-6">
                                        <button
                                            type="button"
                                            onClick={goToGovernanceAssessment}
                                            className="inline-flex items-center justify-center py-3 px-6 text-sm font-semibold rounded-lg text-app-text-label bg-app-bg-muted hover:bg-app-bg-hover transition-all transform active:scale-95 shadow-md"
                                        >
                                            <Zap className="w-4 h-4 mr-2" />
                                            Change Governance
                                        </button>
                                        <button
                                            type="submit"
                                            disabled={!selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked || (activeTab === 'upload' && files.length === 0) || (activeTab === 'text' && !textInput) || processing}
                                            className={`inline-flex items-center justify-center py-3 px-6 text-sm font-semibold rounded-lg text-white transition-all transform active:scale-95 shadow-md ${!selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked || (activeTab === 'upload' && files.length === 0) || (activeTab === 'text' && !textInput) || processing
                                                ? 'bg-gray-300 cursor-not-allowed shadow-none'
                                                : 'bg-app-primary hover:bg-app-primary-hover hover:-translate-y-0.5 hover:shadow-lg'
                                                }`}
                                        >
                                            <Zap className={`w-4 h-4 mr-2 ${processing ? 'animate-pulse' : ''}`} />
                                            {processing ? 'Analyzing...' : selectedProject?.documents.length > 0 ? 'Start Revision Analysis' : 'Start Analysis'}
                                        </button>
                                    </div>
                                </form>
                            </div>
                        )}

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

                                {/* Prerequisites Review Banner */}
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

                                <div id="analysis-content" className="bg-transparent space-y-6">

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
                                                            {/* Optional status indicator dot could go here */}
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
                                                    Executive Summary & Analysis
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

                                                {aiQuestions?.length > 0 ? (
                                                    <div className="space-y-4 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
                                                        {aiQuestions.map((q, i) => (
                                                            <div key={i} className="bg-app-bg-page rounded-lg p-3 border border-app-border-light">
                                                                <p className="text-xs font-medium text-app-text-label mb-2">{q}</p>
                                                                <input
                                                                    type="text"
                                                                    value={(userAnswers || {})[i] || ''}
                                                                    onChange={e => setUserAnswers(prev => ({ ...(prev || {}), [i]: e.target.value }))}
                                                                    className="w-full px-3 py-2 text-xs border border-app-border rounded-md focus:ring-1 focus:ring-app-primary focus:border-app-primary bg-app-bg-card"
                                                                    placeholder="Your answer..."
                                                                />
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <div className="text-center py-8 bg-app-bg-page rounded-lg border border-dashed border-app-border">
                                                        <p className="text-xs text-app-text-light">No specific questions generated.</p>
                                                    </div>
                                                )}

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
                </main>
            )}

            {/* AI Config Modal */}
            {showSettings && (
                <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 backdrop-blur-sm animate-fade-in">
                    <div className="bg-app-bg-card rounded-xl shadow-2xl w-full max-w-md overflow-hidden transform transition-all scale-100">
                        <div className="p-5 border-b border-app-border-light flex justify-between items-center bg-app-bg-page/50">
                            <h2 className="font-bold text-lg text-app-text-main flex items-center">
                                <Settings className="w-5 h-5 mr-2 text-app-primary" />
                                AI Configuration
                            </h2>
                            <button onClick={() => setShowSettings(false)} className="text-app-text-light hover:text-app-text-label transition-colors">✕</button>
                        </div>
                        <div className="p-6">
                            <AIConfig config={aiConfig} onConfigChange={setAiConfig} />
                        </div>
                        <div className="p-4 bg-app-bg-page border-t border-app-border-light flex justify-end">
                            <button
                                onClick={() => setShowSettings(false)}
                                className="px-5 py-2 bg-app-text-main text-white rounded-lg hover:bg-app-text-label font-medium text-sm transition-colors"
                            >
                                Done
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

export default Dashboard;
