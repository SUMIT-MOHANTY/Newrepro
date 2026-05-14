import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useLocation, useParams } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';
import { clearAuthData } from '../utils/auth';
import { sanitizeErrorMessage } from '../utils/errorHandling';
import { customAlert, customPrompt } from '../utils/modalHelpers';
import DOMPurify from 'dompurify';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Settings, FileText, History, User, LogOut, Plus, Zap, Server, Users, Activity, Clock, Download, Menu, CheckCircle2, KeyRound, AlertTriangle, RefreshCw, Info } from 'lucide-react';
import { jsPDF } from 'jspdf';
import { generateRobustPDF } from './robustPdfGenerator';

// import bourntecLogo from '../assets/bourntec_logo.png';
import StatusDashboard from '../components/StatusDashboard';
import Sidebar from '../components/Sidebar';
import GitHubIntegration from '../components/GitHubIntegration';
import AzureDevOpsIntegration from '../components/AzureDevOpsIntegration';
import { upsertDraftProject, getDraftProject } from '../utils/draftProjects';

const GitHubIcon = ({ className = 'w-4 h-4' }) => (
    <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        className={className}
        role="img"
    >
        <path
            fill="currentColor"
            d="M12 2C6.48 2 2 6.58 2 12.26c0 4.5 2.87 8.32 6.84 9.67.5.1.68-.22.68-.48
            0-.24-.01-1.03-.01-1.87-2.49.55-3.01-1.09-3.01-1.09-.45-1.17-1.11-1.48-1.11-1.48-.91-.63.07-.62.07-.62
            1 .07 1.53 1.06 1.53 1.06.9 1.57 2.36 1.12 2.94.86.09-.67.35-1.12.63-1.38-1.99-.23-4.09-1.03-4.09-4.6
            0-1.02.36-1.86.95-2.51-.1-.24-.41-1.21.09-2.52 0 0 .77-.25 2.53.96a8.4 8.4 0 0 1 4.6 0c1.76-1.21 2.53-.96 2.53-.96
            .5 1.31.19 2.28.09 2.52.59.65.95 1.49.95 2.51 0 3.58-2.1 4.37-4.11 4.6.36.32.68.94.68 1.9
            0 1.37-.01 2.48-.01 2.82 0 .27.18.59.69.48A10.02 10.02 0 0 0 22 12.26C22 6.58 17.52 2 12 2Z"
        />
    </svg>
);

const AzureDevOpsIcon = ({ className = 'w-4 h-4' }) => (
    <svg
        viewBox="0 0 16 16"
        aria-hidden="true"
        className={className}
        role="img"
    >
        <defs>
            <linearGradient id="azureDevopsGradient" x1="8" x2="8" y1="14.956" y2="1.026">
                <stop stopColor="#0078D4" />
                <stop offset="0.16" stopColor="#1380DA" />
                <stop offset="0.53" stopColor="#3C91E5" />
                <stop offset="0.82" stopColor="#559CEC" />
                <stop offset="1" stopColor="#5EA0EF" />
            </linearGradient>
        </defs>
        <path
            fill="url(#azureDevopsGradient)"
            d="M15 3.622v8.512L11.5 15l-5.425-1.975v1.958L3.004 10.97l8.951.7V4.005L15 3.622zm-2.984.428L6.994 1v2.001L2.382 4.356 1 6.13v4.029l1.978.873V5.869l9.038-1.818z"
        />
    </svg>
);

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
            prerequisites: lastValidFenced.parsed.prerequisites || [],
            architecture: lastValidFenced.parsed.architecture || null
        };
    }

    // If we got a fenced JSON-like block but parsing failed, still strip it from the report text.
    if (lastJsonLikeFence) {
        const before = source.slice(0, lastJsonLikeFence.index);
        const after = source.slice(lastJsonLikeFence.index + lastJsonLikeFence.fullMatch.length);
        return { report: `${before}${after}`.trim(), questions: [], metrics: null, title: null, prerequisites: [], architecture: null };
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
                prerequisites: parsed.prerequisites || [],
                architecture: parsed.architecture || null
            };
        }
    }

    return { report: source, questions: [], metrics: null, title: null, prerequisites: [], architecture: null };
};

const isLikelyHtml = (content = '') => {
    const htmlTagPattern = /<\/?(?:!doctype|html|head|body|p|div|h[1-6]|ul|ol|li|table|thead|tbody|tr|td|th|strong|em|span|br|hr|blockquote|img|a|section|article|pre|code)\b/i;
    return htmlTagPattern.test(content);
};

const sanitizeHtml = (content = '') => DOMPurify.sanitize(content, { USE_PROFILES: { html: true } });

const normalizeProjectName = (name = '') => String(name || '').trim().toLowerCase();
const ALL_SKIPPED_ANALYZE_BLOCK_MESSAGE = 'Sandbox is not approved. Our IT team will reach out to you soon.';
const isSkipSelectedOption = (label = '') => String(label || '').trim().toLowerCase() === 'skip';

const parseGithubRepoMetaFromUrl = (value = '') => {
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
            provider: 'github',
            url: `https://github.com/${owner}/${repo}.git`,
        };
    } catch {
        return null;
    }
};

const parseAzureRepoMetaFromUrl = (value = '', explicitBranch = '') => {
    const raw = String(value || '').trim();
    if (!raw) return null;

    try {
        const normalized = raw.includes('://') ? raw : `https://${raw}`;
        const urlObj = new URL(normalized);
        const host = urlObj.hostname.toLowerCase();
        const parts = urlObj.pathname.split('/').filter(Boolean).map((p) => decodeURIComponent(p));

        let organization = '';
        let project = '';
        let repo = '';

        if (host.endsWith('dev.azure.com')) {
            if (parts.length < 4 || parts[2].toLowerCase() !== '_git') return null;
            organization = parts[0];
            project = parts[1];
            repo = parts[3];
        } else if (host.endsWith('.visualstudio.com')) {
            organization = host.split('.visualstudio.com')[0];
            if (parts.length < 3 || parts[1].toLowerCase() !== '_git') return null;
            project = parts[0];
            repo = parts[2];
        } else {
            return null;
        }

        repo = repo.replace(/\.git$/i, '').trim();
        if (!organization || !project || !repo) return null;

        const queryVersion = urlObj.searchParams.get('version') || urlObj.searchParams.get('versionDescriptor.version') || '';
        const queryBranch = queryVersion.startsWith('GB') ? queryVersion.slice(2) : queryVersion;
        const branch = String(explicitBranch || queryBranch || '').trim() || null;

        return {
            repo: `${organization}/${project}/${repo}`,
            branch,
            fromLink: true,
            provider: 'azure-devops',
            url: `https://dev.azure.com/${organization}/${project}/_git/${repo}`,
        };
    } catch {
        return null;
    }
};

const buildRepoContextMeta = (context) => {
    const provider = String(context?.provider || 'github').trim().toLowerCase();
    const rawRepo = String(context?.repo || '').trim();
    if (!rawRepo) return null;

    if (provider === 'azure-devops') {
        const normalizedRepo = rawRepo.replace(/^\/+|\/+$/g, '');
        if (!normalizedRepo || normalizedRepo.split('/').filter(Boolean).length < 3) {
            return null;
        }
        const fallbackMeta = parseAzureRepoMetaFromUrl(String(context?.url || '').trim(), context?.branch || '');
        const cloneUrl = String(context?.url || fallbackMeta?.url || '').trim();
        if (!cloneUrl) return null;
        return {
            repo: normalizedRepo,
            branch: String(context?.branch || '').trim() || null,
            source: 'link',
            provider: 'azure-devops',
            url: cloneUrl,
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

const parseRepoMetaFromUrl = (value = '') => {
    return parseGithubRepoMetaFromUrl(value) || parseAzureRepoMetaFromUrl(value);
};

const inferRepoProviderFromUrl = (value = '') => {
    const raw = String(value || '').trim().toLowerCase();
    if (!raw) return null;
    if (raw.includes('dev.azure.com/') || raw.includes('.visualstudio.com/')) {
        return 'azure-devops';
    }
    if (raw.includes('github.com/')) {
        return 'github';
    }
    return null;
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
                        className={`px-3 py-1.5 text-xs font-medium rounded-t-lg transition-all ${
                            activeTabIndex === index
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






const Dashboard = ({
    user: propUser,
    projects: propProjects,
    projectsLoading: propProjectsLoading,
    fetchHistory: refreshProjects,
    selectedProjectKey: propSelectedProjectKey,
    setSelectedProjectKey: propSetSelectedProjectKey,
    showSettings: propShowSettings,
    setShowSettings: propSetShowSettings,
    currentView: propCurrentView,
    isNewProjectMode,
    fetchRoadmapData,
    selectedRole,
    setSelectedRole,
    aiConfig,
    setAiConfig,
}) => {
    const { projectToken } = useParams();
    const [user, setUser] = useState(propUser || null);
    const [analyzeWithAi] = useState(true);
    const navigate = useNavigate();

    const [streamResponse] = useState(false);

    const [history, setHistory] = useState([]);
    const [governanceHistory, setGovernanceHistory] = useState([]);
    const [internalProjects, setInternalProjects] = useState([]);
    const projects = propProjects || internalProjects;
    const projectsLoading = propProjectsLoading ?? false;
    const setProjects = setInternalProjects;

    const [internalSelectedProjectKey, setInternalSelectedProjectKey] = useState('');
    const selectedProjectKey = propSelectedProjectKey !== undefined ? propSelectedProjectKey : internalSelectedProjectKey;
    const setSelectedProjectKey = propSetSelectedProjectKey || setInternalSelectedProjectKey;

    // -- Per-Project State Management --
    const [projectStates, setProjectStates] = useState({});

    const getProjectState = (key) => {
        const state = projectStates[key] || {
            files: [], linkedFiles: [], textInput: '', activeTab: 'upload', processing: false,
            result: null, error: '', userFeedback: '', aiQuestions: [],
            userAnswers: {}, revisionUnlocked: false, revisionReason: '',
            progress: 0, progressMessage: '',
            urlInput: '', urlRequirements: '', urlSource: '', urlFetchSummary: null,
            urlFetching: false,
            skillFiles: [] // Add skills files state
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
    const projectStateUpdaterRef = useRef(setProjectState);
    projectStateUpdaterRef.current = setProjectState;

    const activeState = getProjectState(selectedProjectKey);
    const {
        files = [], linkedFiles = [], textInput, activeTab, processing, result, error,
        userFeedback, aiQuestions, userAnswers, revisionUnlocked,
        revisionReason, progress, progressMessage,
        urlInput = '', urlRequirements = '', urlSource = '', urlFetchSummary = null,
        urlFetching = false,
        skillFiles = [] // Add skills files to destructuring
    } = activeState;

    // Helpers to update active project state from UI components natively 
    const setFiles = (v) => setProjectState(selectedProjectKey, { files: typeof v === 'function' ? v(activeState.files || []) : v });
    const setLinkedFiles = (v) => setProjectState(selectedProjectKey, { linkedFiles: typeof v === 'function' ? v(activeState.linkedFiles || []) : v });
    const setSkillFiles = (v) => setProjectState(selectedProjectKey, { skillFiles: typeof v === 'function' ? v(activeState.skillFiles || []) : v });
    const setTextInput = (v) => setProjectState(selectedProjectKey, { textInput: typeof v === 'function' ? v(activeState.textInput) : v });
    const setUrlInput = (v) => setProjectState(selectedProjectKey, { urlInput: typeof v === 'function' ? v(activeState.urlInput) : v });
    const setUrlRequirements = (v) => setProjectState(selectedProjectKey, { urlRequirements: typeof v === 'function' ? v(activeState.urlRequirements) : v });
    const setActiveTab = (v) => setProjectState(selectedProjectKey, { activeTab: typeof v === 'function' ? v(activeState.activeTab) : v });
    const setError = (v) => setProjectState(selectedProjectKey, { error: typeof v === 'function' ? v(activeState.error) : v });
    const setUserFeedback = (v) => setProjectState(selectedProjectKey, { userFeedback: typeof v === 'function' ? v(activeState.userFeedback) : v });
    const setUserAnswers = (v) => setProjectState(selectedProjectKey, { userAnswers: typeof v === 'function' ? v(activeState.userAnswers) : v });

    const location = useLocation();

    const currentView = propCurrentView || (location.pathname === '/status' ? 'statusDashboard' : 'main');

    // Signal to AppLayout whether we are showing analysis results or the upload form.
    // This drives the roadmap highlighting (Requirement Screening vs Agent Analysis).
    useEffect(() => {
        if (currentView === 'main') {
            if (result) {
                sessionStorage.setItem('dashboard_showing_results', 'true');
            } else {
                sessionStorage.removeItem('dashboard_showing_results');
            }
        }
        return () => {
            // Clean up when leaving the dashboard
            sessionStorage.removeItem('dashboard_showing_results');
        };
    }, [result, currentView]);

    const [githubLinkUrl, setGithubLinkUrl] = useState('');
    const [githubLinkToken, setGithubLinkToken] = useState('');
    const [githubAuthMode, setGithubAuthMode] = useState('pat');
    const [githubLinkUsername, setGithubLinkUsername] = useState('');
    const [githubLinkPassword, setGithubLinkPassword] = useState('');
    const [githubLinkParsing, setGithubLinkParsing] = useState(false);
    const [githubLinkError, setGithubLinkError] = useState('');
    const [repoLinkProvider, setRepoLinkProvider] = useState('github');
    const [azureLinkUrl, setAzureLinkUrl] = useState('');
    const [azureLinkToken, setAzureLinkToken] = useState('');
    const [azureLinkBranch, setAzureLinkBranch] = useState('');
    const [azureLinkParsing, setAzureLinkParsing] = useState(false);
    const [azureLinkError, setAzureLinkError] = useState('');
    const [azureProjectRepos, setAzureProjectRepos] = useState([]);
    const [azureProjectReposLoading, setAzureProjectReposLoading] = useState(false);
    const [showAzureRepoSelector, setShowAzureRepoSelector] = useState(false);
    const [azureProjectUrl, setAzureProjectUrl] = useState('');
    const [isOAuthRepoSelected, setIsOAuthRepoSelected] = useState(false);
    
    // Track if credentials are locked (saved and can only be changed once)
    const [credentialsLocked, setCredentialsLocked] = useState(false);
    const [hasChangedCredentials, setHasChangedCredentials] = useState(false);

    const [governanceContext, setGovernanceContext] = useState(null);
    const [repoContext, setRepoContext] = useState(null);
    const selectedProject = projects.find((project) => project.key === selectedProjectKey) || null;
    
    const saveRepoContextToStorage = (context) => {
        try {
            console.log('Saving repo context to storage:', context);
            localStorage.setItem('repoContext', JSON.stringify(context));
            sessionStorage.setItem('repoContext', JSON.stringify(context));
        } catch (err) {
            console.warn('Failed to save repo context to storage:', err);
        }
    };

    const clearRepoContextFromStorage = () => {
        try {
            localStorage.removeItem('repoContext');
            sessionStorage.removeItem('repoContext');
        } catch (err) {
            console.warn('Failed to clear repo context from storage:', err);
        }
    };
    
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
    const readStoredRepoContextMetaForProject = useCallback((projectKey = selectedProjectKey) => {
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

        for (const key of keyCandidates) {
            const storageKey = `repo_context_meta_${key}`;
            const raw = sessionStorage.getItem(storageKey) || localStorage.getItem(storageKey);
            if (!raw) continue;
            try {
                const parsed = JSON.parse(raw);
                if (parsed && typeof parsed === 'object') {
                    return parsed;
                }
            } catch {
                // Ignore malformed cache entry.
            }
        }
        return null;
    }, [selectedProjectKey, selectedProject, governanceContext]);

    const saveGitCredentialsToBackend = async (repoUrl, token, projectKey = selectedProjectKey) => {
        try {
            const authToken = localStorage.getItem('token');
            if (!authToken || !projectKey) return;

            // Find an agent to update (use the first non-system agent)
            const agentsUrl = new URL(API_ENDPOINTS.AGENTS);
            agentsUrl.searchParams.set('project_token', projectKey);
            const agentsRes = await fetch(agentsUrl.toString(), {
                headers: { Authorization: `Bearer ${authToken}` },
            });
            
            if (!agentsRes.ok) return;
            
            const agentsData = await agentsRes.json().catch(() => ({}));
            const agentList = Array.isArray(agentsData?.agents) ? agentsData.agents : [];
            const targetAgent = agentList.find((a) => a?.id !== 'agent_03' && a?.id !== 'agent_04') || agentList[0];
            
            if (!targetAgent?.id) return;

            // Update the agent's Git credentials
            const updateUrl = new URL(API_ENDPOINTS.AGENT_UPDATE(targetAgent.id));
            updateUrl.searchParams.set('project_token', projectKey);
            const gitPayload = { git_repo_url: repoUrl, git_token: token };

            await fetch(updateUrl.toString(), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${authToken}`,
                },
                body: JSON.stringify(gitPayload),
            });
        } catch (err) {
            console.warn('Failed to save Git credentials to backend:', err);
        }
    };

    const handleChangeCredentials = () => {
        if (credentialsLocked && hasChangedCredentials) {
            customAlert('Credentials can only be changed once after initial setup. Please contact support if you need to change them again.');
            return;
        }
        // Clear current credentials to allow new entry
        setGithubLinkUrl('');
        setGithubLinkToken('');
        setAzureLinkUrl('');
        setAzureLinkToken('');
        setAzureLinkBranch('');
        setCredentialsLocked(false);
    };

    const fetchRepoContextForAnalysis = async (repoUrl, token, provider, projectKey = selectedProjectKey) => {
        try {
            const authToken = localStorage.getItem('token');
            if (!authToken || !repoUrl) return;

            // First validate the connection using the working endpoint
            const validateResponse = await fetch(API_ENDPOINTS.GIT_VALIDATE_CONNECTION, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${authToken}`,
                },
                body: JSON.stringify({
                    repo_url: repoUrl,
                    pat: token || null,
                    provider: provider,
                }),
            });

            if (!validateResponse.ok) {
                const errorData = await validateResponse.json();
                throw new Error(errorData.detail || 'Failed to validate repository connection');
            }

            const validationData = await validateResponse.json();
            
            // Now fetch the actual repo context using the appropriate endpoint
            const endpoint = provider === 'azure-devops'
                ? API_ENDPOINTS.AZURE_DEVOPS_REPO_CONTEXT
                : API_ENDPOINTS.GITHUB_REPO_CONTEXT;

            const payload = provider === 'azure-devops'
                ? { repo_url: validationData.normalized_url || repoUrl, token }
                : {
                    owner: validationData.owner,
                    repo: validationData.repo,
                    token: token || null,
                    branch: 'main'
                };

            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${authToken}`,
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to fetch repository context');
            }

            const data = await response.json();
            
            // Build repo context from response
            const nextRepoContext = {
                repo: provider === 'azure-devops' 
                    ? validationData.repo || data.repo || repoUrl 
                    : `${validationData.owner}/${validationData.repo}`,
                branch: data.branch || 'main',
                context: data.context,
                fromLink: true,
                provider,
                url: validationData.normalized_url || repoUrl,
            };

            setRepoContext(nextRepoContext);
            persistRepoContextMetaForProject(nextRepoContext, projectKey);
            saveRepoContextToStorage(nextRepoContext);
        } catch (err) {
            console.warn('Fetch repo context for analysis failed:', err);
            throw err;
        }
    };

    const handleRepositoryOnlyAnalysisInDashboard = async (taskKey) => {
        if (!hasGovernanceAssessment) {
            // Navigate to governance first for repo-only analysis
            setProjectState(taskKey, {
                processing: false,
                progress: 85,
                progressMessage: 'Repository context ready. Continue with Governance.',
                result: null,
            });
            
            // Save a pending analysis entry for repository-only case
            await savePendingScreeningToHistory({
                filename: `Repository Analysis - ${repoContext.repo || 'Unknown Repository'}`,
                markdown: repoContext.context,
                taskKey,
                repoContextState: repoContext,
                isRepositoryOnly: true,
            });
            
            navigate('/new-project/governance');
            return;
        }

        // If governance is already complete, navigate directly to AgentAnalysis
        // The AgentAnalysis component will handle the repository-only analysis
        navigate('/agent-analysis');
    };

    const loadSavedGitCredentials = useCallback(async (projectKey = selectedProjectKey) => {
        try {
            const authToken = localStorage.getItem('token');
            if (!authToken || !projectKey) return;

            const agentsUrl = new URL(API_ENDPOINTS.AGENTS);
            agentsUrl.searchParams.set('project_token', projectKey);
            const agentsRes = await fetch(agentsUrl.toString(), {
                headers: { Authorization: `Bearer ${authToken}` },
            });
            
            if (!agentsRes.ok) return;
            
            const agentsData = await agentsRes.json().catch(() => ({}));
            const agentList = Array.isArray(agentsData?.agents) ? agentsData.agents : [];
            
            // Find first agent with Git credentials
            const agentWithCreds = agentList.find((a) => a?.git_repo_url);
            
            if (agentWithCreds?.git_repo_url) {
                const repoUrl = agentWithCreds.git_repo_url;
                const hasToken = agentWithCreds.has_git_token;
                
                // Determine provider from URL
                const isAzure = repoUrl.includes('dev.azure.com') || repoUrl.includes('visualstudio.com');
                
                if (isAzure) {
                    setAzureLinkUrl(repoUrl);
                    setRepoLinkProvider('azure-devops');
                    setIsOAuthRepoSelected(false);
                    // Note: We can't retrieve the actual token for security reasons
                    // but we know it exists if hasToken is true
                } else {
                    setGithubLinkUrl(repoUrl);
                    setRepoLinkProvider('github');
                    // For GitHub, also check if using OAuth or PAT
                    if (hasToken && !agentWithCreds.git_token) {
                        // Token exists on backend but not returned (security)
                        setGithubAuthMode('pat');
                    }
                }
                
                // Lock credentials if they were previously saved
                setCredentialsLocked(true);
            }
        } catch (err) {
            console.warn('Failed to load saved Git credentials:', err);
        }
    }, [selectedProjectKey]);

    // Load saved Git credentials when project changes
    useEffect(() => {
        if (selectedProjectKey) {
            loadSavedGitCredentials(selectedProjectKey);
        } else {
            // Reset when no project selected
            setCredentialsLocked(false);
            setHasChangedCredentials(false);
        }
    }, [selectedProjectKey, loadSavedGitCredentials]);

    useEffect(() => {
        const providerFromContext = String(repoContext?.provider || '').trim().toLowerCase();
        if (providerFromContext === 'azure-devops' || providerFromContext === 'github') {
            setRepoLinkProvider(providerFromContext);
            if (providerFromContext === 'azure-devops') {
                setIsOAuthRepoSelected(false);
            }
            return;
        }

        const storedMeta = readStoredRepoContextMetaForProject(selectedProjectKey);
        const providerFromStored = String(storedMeta?.provider || '').trim().toLowerCase();
        if (providerFromStored === 'azure-devops' || providerFromStored === 'github') {
            setRepoLinkProvider(providerFromStored);
            if (providerFromStored === 'azure-devops') {
                setIsOAuthRepoSelected(false);
            }
        }
    }, [selectedProjectKey, repoContext?.provider, readStoredRepoContextMetaForProject]);

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
    
    // Check if governance assessment exists for current revision
    // If revisionUnlocked is true, we need new governance for the revision
    const hasGovernanceAssessment = revisionUnlocked 
        ? false // Revision needs new governance
        : Boolean(selectedProject?.governanceResultId || governanceContext?.result_id);
    
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
        const parsedAnalysis = parseStoredDocumentAnalysis(doc);

        const governanceMeta = parsedAnalysis?.governanceContext || {};
        const projectMeta = parsedAnalysis?.projectMeta || {};
        const projectName = projectMeta.project_name || governanceMeta.project_name || 'Unassigned Project';
        const governanceResultId = projectMeta.governance_result_id || governanceMeta.result_id || null;
        const projectToken = projectMeta.project_token || governanceMeta.project_token || null;
        const revisionReason = projectMeta.revision_reason || null;
        const revisionNumber = projectMeta.revision_number || null;

        return {
            parsedAnalysis,
            projectName,
            governanceResultId,
            projectToken,
            revisionReason,
            revisionNumber,
        };
    }, []);

    const persistHistoryDocument = useCallback(async (payload, documentId = null) => {
        const token = localStorage.getItem('token');
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
            handleLogout();
            return null;
        }

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || 'History save failed');
        }

        return response.json();
    }, [handleLogout]);

    const savePendingScreeningToHistory = useCallback(async ({
        filename,
        markdown,
        taskKey = selectedProjectKey,
        repoContextState = repoContext,
    }) => {
        if (!filename || !markdown) return null;

        const project = projects.find((p) => p.key === taskKey);
        const currentRevisionCount = project?.documents?.length || 0;
        const nextRevisionNumber = currentRevisionCount + 1;
        const repoContextMeta = buildRepoContextMeta(repoContextState);
        const pendingAnalysis = {
            screening_status: 'pending_governance_analysis',
            governanceContext: null,
            repoContextState: repoContextState || null,
            repoContextMeta: repoContextMeta || null,
            projectMeta: {
                project_name: project?.name || 'Project',
                project_token: project?.projectToken || taskKey || null,
                governance_result_id: project?.governanceResultId || null,
                revision_number: nextRevisionNumber,
                revision_reason: revisionReason || null,
                repo_context: repoContextMeta || null,
            }
        };

        try {
            const savedDoc = await persistHistoryDocument({
                filename,
                content_preview: `${String(markdown).substring(0, 200)}...`,
                full_content: markdown,
                analysis_result: JSON.stringify(pendingAnalysis),
            });

            if (!savedDoc) return null;

            // CRITICAL: Preserve existing credentials when updating draft project
            const existingDraft = getDraftProject(taskKey);
            upsertDraftProject({
                key: taskKey,
                name: project?.name || 'Project',
                status: 'screening_complete',
                latestRevision: nextRevisionNumber,
                submissionDate: new Date().toISOString(),
                // Preserve credentials from existing draft
                client_id: existingDraft?.client_id || project?.client_id || null,
                client_secret: existingDraft?.client_secret || project?.client_secret || null,
            });
            fetchHistory();
            refreshProjects?.();
            return savedDoc;
        } catch (e) {
            console.error('Pending screening save failed', e);
            throw e;
        }
    }, [selectedProjectKey, projects, revisionReason, repoContext, persistHistoryDocument, fetchHistory, refreshProjects]);

    // Save history
    const saveToHistory = async (newResult, taskKey = selectedProjectKey, analysisRepoContext = repoContext) => {
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
                sections: newResult.extraction?.sections || [], // Store structured sections
                projectMeta: {
                    project_name: project?.name || governanceContext?.project_name || 'Project',
                    project_token: project?.projectToken || taskKey || null,
                    governance_result_id: governanceContext?.result_id || project?.governanceResultId || null,
                    revision_number: nextRevisionNumber,
                    revision_reason: revisionReason || null,
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
                // CRITICAL: Preserve existing credentials when updating draft project
                const existingDraft = getDraftProject(taskKey);
                upsertDraftProject({
                    key: taskKey,
                    name: project?.name || governanceContext?.project_name || 'Project',
                    status: 'analysis_complete',
                    latestRevision: nextRevisionNumber,
                    submissionDate: new Date().toISOString(),
                    // Preserve credentials from existing draft
                    client_id: existingDraft?.client_id || project?.client_id || null,
                    client_secret: existingDraft?.client_secret || project?.client_secret || null,
                });
                setProjectState(taskKey, prev => ({
                    result: { ...prev.result, id: savedDoc.id, revisionNumber: nextRevisionNumber },
                    revisionUnlocked: false,
                    revisionReason: ''
                }));
                fetchHistory();
                refreshProjects?.();
                
                // Always navigate to agent analysis after successful save
                // The governance check happens in handleUpload before this
                navigate('/agent-analysis');
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
        if (requestedTab === 'upload' || requestedTab === 'text' || requestedTab === 'url') {
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
                const hasCompletedAnalysis = docs.some((doc) => hasCompletedDocumentAnalysis(doc));
                return {
                    ...project,
                    documents: docs,
                    latestDocument: docs[0] || null,
                    latestRevision: docs.length,
                    status: hasCompletedAnalysis ? 'analysis_complete' : (docs.length > 0 ? 'screening_complete' : 'ready_for_upload'),
                };
            })
            .sort((a, b) => {
                const aDate = new Date(a.submissionDate || a.latestDocument?.upload_date || 0).getTime();
                const bDate = new Date(b.submissionDate || b.latestDocument?.upload_date || 0).getTime();
                return bDate - aDate;
            });

        setProjects(builtProjects);
    }, [governanceHistory, history, extractProjectMetaFromDocument, setProjects]);

    // Redirect to new project page if no projects exist and not in new project mode
    useEffect(() => {
        if (!projectsLoading && projects.length === 0 && !isNewProjectMode) {
            // Give a small delay to ensure projects have been loaded
            const timer = setTimeout(() => {
                if (projects.length === 0) {
                    navigate('/new-project');
                }
            }, 500);
            return () => clearTimeout(timer);
        }
    }, [projects.length, projectsLoading, isNewProjectMode, navigate]);

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
    }, [projects, selectedProjectKey, governanceContext, isNewProjectMode, projectToken, setSelectedProjectKey]);

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
            if (isPendingGovernanceAnalysis(parsedAnalysis)) {
                setError('Requirement Screening is saved. Complete Governance to start Agent Analysis.');
                return;
            }
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
                        num_pages: null,
                        sections: parsedAnalysis.sections || [] // Preserve sections from saved analysis
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
        } else if (activeTab === 'skills') {
            setSkillFiles(selectedFiles);
        } else {
            setFiles(selectedFiles);
        }
    };

    const handleTextChange = (e) => {
        setTextInput(e.target.value);
    };

    const handleUrlInputChange = (e) => {
        setUrlInput(e.target.value);
    };

    const fetchRequirementsFromUrl = async (urlValue, taskKey = selectedProjectKey) => {
        const token = localStorage.getItem('token');
        const normalizedUrl = String(urlValue || '').trim();
        if (!normalizedUrl) {
            throw new Error('Please enter a website URL.');
        }

        setProjectState(taskKey, {
            urlFetching: true,
            error: '',
            progress: 20,
            progressMessage: 'Fetching website requirements...'
        });

        try {
            const response = await fetch(API_ENDPOINTS.DOCUMENTS_EXTRACT_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ url: normalizedUrl })
            });

            if (response.status === 401) {
                handleLogout();
                return null;
            }

            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(data.detail || 'Failed to fetch URL requirements');
            }

            const markdown = String(data.markdown || '').trim();
            if (!markdown) {
                throw new Error('No readable requirement content found on that URL.');
            }

            setProjectState(taskKey, {
                urlRequirements: markdown,
                urlSource: String(data.url || normalizedUrl),
                urlFetchSummary: data.summary || null,
                progress: 40,
                progressMessage: 'Website content processed.'
            });
            return data;
        } finally {
            setProjectState(taskKey, { urlFetching: false });
        }
    };

    const handleFetchUrlRequirements = async () => {
        try {
            await fetchRequirementsFromUrl(urlInput, selectedProjectKey);
        } catch (err) {
            console.error('URL fetch error:', err);
            setError(sanitizeErrorMessage(err));
        }
    };

    const handleUpload = async (e) => {
        const taskKey = selectedProjectKey;
        e.preventDefault();
        
        if (!selectedProject) {
            setError('Select a project from the sidebar before uploading a BRD.');
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

        // Check if at least ONE input is provided
        const hasFiles = files.length > 0;
        const hasLinkedFiles = linkedFiles.length > 0;
        const hasText = textInput.trim().length > 0;
        const hasUrl = urlInput.trim().length > 0 || urlRequirements.trim().length > 0;
        const hasRepo = repoContext?.context;
        const hasSkills = skillFiles.length > 0;

        if (!hasFiles && !hasLinkedFiles && !hasText && !hasUrl && !hasRepo && !hasSkills) {
            setError('Please provide at least one input: upload files, write text, add URL, connect repository, or upload skills.');
            return;
        }

        // Persist repository choice for this project
        if (repoLinkProvider === 'azure-devops' && azureLinkUrl) {
            const repoFromInput = parseAzureRepoMetaFromUrl(azureLinkUrl, '');
            if (repoFromInput) {
                persistRepoContextMetaForProject(repoFromInput, taskKey);
            }
            
            // Save Git credentials to backend for use by agents
            if (azureLinkUrl && azureLinkToken) {
                await saveGitCredentialsToBackend(azureLinkUrl, azureLinkToken, taskKey);
                if (credentialsLocked) {
                    setHasChangedCredentials(true);
                }
                setCredentialsLocked(true);
                
                // Fetch repo context if not loaded
                if (!repoContext) {
                    try {
                        await fetchRepoContextForAnalysis(azureLinkUrl, azureLinkToken, 'azure-devops', taskKey);
                    } catch (err) {
                        console.warn('Failed to fetch repo context for analysis:', err);
                    }
                }
            }
        } else if (repoLinkProvider === 'github' && githubLinkUrl) {
            const repoFromInput = parseRepoMetaFromUrl(githubLinkUrl);
            if (repoFromInput) {
                persistRepoContextMetaForProject(repoFromInput, taskKey);
            }
            
            // Save Git credentials to backend
            const gitToken = githubAuthMode === 'pat' ? githubLinkToken : githubLinkPassword;
            if (githubLinkUrl && gitToken) {
                await saveGitCredentialsToBackend(githubLinkUrl, gitToken, taskKey);
                if (credentialsLocked) {
                    setHasChangedCredentials(true);
                }
                setCredentialsLocked(true);
                
                // Fetch repo context if not loaded
                if (!repoContext) {
                    try {
                        await fetchRepoContextForAnalysis(githubLinkUrl, gitToken, 'github', taskKey);
                    } catch (err) {
                        console.warn('Failed to fetch repo context for analysis:', err);
                    }
                }
            }
        }

        setProjectState(taskKey, { processing: true, error: '', result: null, aiQuestions: [], userAnswers: {}, userFeedback: '' });

        try {
            const token = localStorage.getItem('token');
            let combinedMarkdown = '';
            let combinedHtml = '';
            let filename = '';
            const contentSections = [];

            setProjectState(taskKey, { progress: 10, progressMessage: `Preparing content for ${selectedProject.name}...` });

            // 1. Process uploaded files (Upload tab)
            if (hasFiles) {
                const formData = new FormData();
                for (let i = 0; i < files.length; i++) {
                    formData.append('files', files[i]);
                }

                const uploadResponse = await fetch(API_ENDPOINTS.DOCUMENTS_UPLOAD, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });

                if (uploadResponse.status === 401) {
                    handleLogout();
                    return;
                }

                if (uploadResponse.ok) {
                    const uploadData = await uploadResponse.json();
                    contentSections.push({
                        title: 'UPLOADED DOCUMENTS',
                        markdown: uploadData.markdown,
                        html: uploadData.html
                    });
                    filename = uploadData.filename;
                }
                setProjectState(taskKey, { progress: 20, progressMessage: 'Uploaded files processed...' });
            }

            // 2. Process linked files (Linked Doc tab)
            if (hasLinkedFiles) {
                const formData = new FormData();
                for (let i = 0; i < linkedFiles.length; i++) {
                    formData.append('files', linkedFiles[i]);
                }

                const uploadResponse = await fetch(API_ENDPOINTS.DOCUMENTS_UPLOAD, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });

                if (uploadResponse.ok) {
                    const uploadData = await uploadResponse.json();
                    contentSections.push({
                        title: 'LINKED PROJECT DOCUMENTS',
                        markdown: uploadData.markdown,
                        html: uploadData.html
                    });
                    if (!filename) filename = uploadData.filename;
                }
                setProjectState(taskKey, { progress: 30, progressMessage: 'Linked documents processed...' });
            }

            // 3. Process text input (Text tab)
            if (hasText) {
                contentSections.push({
                    title: 'MANUAL TEXT INPUT',
                    markdown: textInput,
                    html: `<pre style="white-space: pre-wrap; font-family: inherit;">${textInput}</pre>`
                });
                if (!filename) filename = 'Manual_Input_' + new Date().toISOString().slice(0, 10);
                setProjectState(taskKey, { progress: 40, progressMessage: 'Text input processed...' });
            }

            // 4. Process URL (URL tab)
            if (hasUrl) {
                let urlMarkdown = urlRequirements.trim();
                let urlSourceUrl = urlSource || urlInput.trim();
                
                if (!urlMarkdown && urlInput.trim()) {
                    const fetchedData = await fetchRequirementsFromUrl(urlInput, taskKey);
                    if (fetchedData) {
                        urlMarkdown = fetchedData.markdown;
                        urlSourceUrl = fetchedData.url || urlInput.trim();
                    }
                }

                if (urlMarkdown) {
                    contentSections.push({
                        title: `WEBSITE REQUIREMENTS (${urlSourceUrl})`,
                        markdown: urlMarkdown,
                        html: null
                    });
                    if (!filename) filename = 'URL_Requirements_' + new Date().toISOString().slice(0, 10);
                }
                setProjectState(taskKey, { progress: 50, progressMessage: 'URL content processed...' });
            }

            // 5. Process skill files (Skills tab)
            if (hasSkills) {
                const formData = new FormData();
                for (let i = 0; i < skillFiles.length; i++) {
                    formData.append('files', skillFiles[i]);
                }

                const uploadResponse = await fetch(API_ENDPOINTS.DOCUMENTS_UPLOAD, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });

                if (uploadResponse.ok) {
                    const uploadData = await uploadResponse.json();
                    contentSections.push({
                        title: 'SKILLS & CONTEXT FILES',
                        markdown: uploadData.markdown,
                        html: uploadData.html
                    });
                }
                setProjectState(taskKey, { progress: 60, progressMessage: 'Skills processed...' });
            }

            // 6. Combine all sections
            combinedMarkdown = contentSections.map(section => 
                `\n\n--- ${section.title} ---\n\n${section.markdown}`
            ).join('');

            combinedHtml = contentSections.map(section => 
                section.html ? `<div class="document-separator"><h2>${section.title}</h2></div>${section.html}` : ''
            ).filter(Boolean).join('');

            if (!filename) {
                filename = 'Combined_Analysis_' + new Date().toISOString().slice(0, 10);
            } else {
                filename += ' (Combined)';
            }

            setProjectState(taskKey, { progress: 70, progressMessage: 'All content combined...' });

            // Handle repository-only analysis (no other content)
            if (hasRepo && !combinedMarkdown.trim()) {
                await handleRepositoryOnlyAnalysisInDashboard(taskKey);
                return;
            }

            if (isAllGovernanceSkippedCase && analyzeWithAi) {
                setProjectState(taskKey, {
                    progress: 100,
                    progressMessage: 'Analysis blocked pending IT approval.',
                    error: ''
                });
                navigate('/new-project/governance');
                return;
            }

            if (!hasGovernanceAssessment) {
                setProjectState(taskKey, {
                    progress: 85,
                    progressMessage: 'Requirement screening complete. Saving BRD before Governance...',
                });

                await savePendingScreeningToHistory({
                    filename,
                    markdown: combinedMarkdown,
                    taskKey,
                    repoContextState: repoContext,
                });

                setProjectState(taskKey, {
                    processing: false,
                    progress: 100,
                    progressMessage: 'Requirement screening complete. Continue with Governance.',
                    result: null,
                });
                navigate('/new-project/governance');
                return;
            }

            // Set initial result with structured content
            const initialResult = {
                filename: filename,
                extraction: {
                    markdown: combinedMarkdown,
                    html: combinedHtml,
                    num_pages: null,
                    sections: contentSections.map(s => ({ title: s.title, content: s.markdown })) // Add structured sections
                },
                analysis: analyzeWithAi ? { analysis: '', reasoning: '' } : null
            };
            setProjectState(taskKey, { result: initialResult });

            // Step 2: Analyze with AI
            if (analyzeWithAi) {
                // Combine all content including repository context
                let finalContent = combinedMarkdown;
                if (repoContext?.context) {
                    finalContent += `\n\n--- REPOSITORY CONTEXT ---\n\n${repoContext.context}`;
                }

                const aiPayload = {
                    document_content: finalContent,
                    api_url: aiConfig?.apiUrl || undefined,
                    api_key: aiConfig?.apiKey || undefined,
                    model: aiConfig?.model || undefined,
                    stream: streamResponse,
                    governance_context: governanceContext || undefined
                };

                if (streamResponse) {
                    setProjectState(taskKey, { progress: 75, progressMessage: 'Initializing AI task...' });
                    await streamAnalysis(aiPayload, token, initialResult, taskKey);
                } else {
                    setProjectState(taskKey, { progress: 75, progressMessage: 'Initializing AI task...' });
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
    const fetchAnalysis = async (
        payload,
        token,
        initialContext = null,
        taskKey = selectedProjectKey,
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
                handleLogout();
                return;
            }

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Analysis failed');
            }

            const data = await response.json();
            const { report, questions, metrics, title, prerequisites, architecture } = parseAIResponse(data.analysis || '');
            if (questions.length > 0) setProjectState(taskKey, { aiQuestions: questions });

            const effectiveGovernanceContext = analysisOptions.governanceContext || governanceContext || null;
            const effectiveRepoContext = analysisOptions.repoContext || repoContext || null;
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
                    architecture: architecture,
                    userAnswers: userAnswers,
                    userFeedback: userFeedback,
                    governanceContext: effectiveGovernanceContext,
                    repoContextMeta: buildRepoContextMeta(effectiveRepoContext),
                }
            };
            setProjectState(taskKey, { result: finalResult, progress: 100, progressMessage: 'Analysis complete!' });
            await saveToHistory(finalResult, taskKey, effectiveRepoContext);
            // Project creation is now done in Project Initiation step, no need to create here
            // createProjectFromMetrics(finalResult, metrics);

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

            // NOTE:
            // Do NOT create the external task project from Dashboard/initiation.
            // Project creation must happen during Task Creation (/api/agent/auto-generate/)
            // so that the project deadline is derived strictly from the selected process_mode.
        } catch (err) {
            console.error("Project generation error:", err);
        }
    };

    const streamAnalysis = async (
        payload,
        token,
        initialContext = null,
        taskKey = selectedProjectKey,
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

            setProjectState(taskKey, { progress: 85, progressMessage: 'Generating analysis report...' });


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
                            const { report, questions, metrics, prerequisites, architecture } = parseAIResponse(aiText);
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
                                        prerequisites: prerequisites,
                                        architecture: architecture
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
            const { report, questions, metrics, title, prerequisites, architecture } = parseAIResponse(aiText);

            const effectiveGovernanceContext = analysisOptions.governanceContext || governanceContext || null;
            const effectiveRepoContext = analysisOptions.repoContext || repoContext || null;
            const finalFilename = title || (initialContext || result).filename;

            const finalResult = {
                ...(initialContext || result), // Use scope content
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
            setProjectState(taskKey, {
                result: finalResult,
                progress: 100,
                progressMessage: 'Analysis complete!',
                aiQuestions: questions?.length ? questions : []
            });
            await saveToHistory(finalResult, taskKey, effectiveRepoContext);
            // Project creation is now done in Project Initiation step, no need to create here
            // createProjectFromMetrics(finalResult, metrics);

            // Auto-refresh roadmap stepper after analysis completes
            if (fetchRoadmapData && selectedProjectKey) {
                fetchRoadmapData(selectedProjectKey);
            }
        } catch (err) {
            setProjectState(taskKey, { error: `Stream Error: ${err.message}` });
        }
    };
    const fetchAnalysisRef = useRef(fetchAnalysis);
    const streamAnalysisRef = useRef(streamAnalysis);
    fetchAnalysisRef.current = fetchAnalysis;
    streamAnalysisRef.current = streamAnalysis;

    // Analysis triggering is now handled entirely by AgentAnalysis.jsx
    // Dashboard should not trigger analysis automatically anymore
    // This useEffect is kept for potential future use but currently disabled
    useEffect(() => {
        // Don't auto-trigger analysis - AgentAnalysis.jsx handles all analysis triggering now
        // Analysis should only happen on /agent-analysis page after clicking "Proceed to Agent Analysis"
        return;
    }, [
        selectedProject,
        selectedProjectKey,
        hasGovernanceAssessment,
        governanceContext,
        processing,
        result,
        analyzeWithAi,
        location.pathname,
    ]);

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
            // Build metrics from result
            const metricSource = result.analysis?.metrics || {};
            const metrics = [
                { label: 'Deployment', value: metricSource?.deployment || 'TBD' },
                { label: 'Resources', value: metricSource?.resources || 'TBD' },
                { label: 'Complexity', value: metricSource?.complexity || 'TBD' },
                { label: 'Timeline (For Developer Only Mode)', value: metricSource?.timeline || 'TBD' }
            ];

            // Get questions and answers
            const questions = result.analysis?.questions?.length ? result.analysis.questions : aiQuestions;
            const answers = result.analysis?.userAnswers || userAnswers;

            // Generate robust PDF (AI-model-agnostic)
            generateRobustPDF(result, {
                filename: result.filename || 'Report',
                title: 'BRD Analysis Report',
                metrics: metrics,
                questions: questions,
                answers: answers,
                additionalNotes: result.analysis?.userFeedback || userFeedback || '',
                reasoningText: result.analysis?.reasoning || ''
            });
        } catch (err) {
            console.error('PDF generation failed', err);
            setError(sanitizeErrorMessage(err));
        }
    };

    const handleLoadGithubUrl = async () => {
        setGithubLinkError('');
        setAzureLinkError('');
        if (!githubLinkUrl.includes('github.com/')) {
            setGithubLinkError('Please enter a valid GitHub URL (e.g. https://github.com/owner/repo)');
            return;
        }
        if (githubAuthMode === 'basic') {
            const username = String(githubLinkUsername || '').trim();
            const password = String(githubLinkPassword || '');
            if (!username || !password) {
                setGithubLinkError('Enter both GitHub username and password, or switch to PAT mode.');
                return;
            }
        }

        try {
            setGithubLinkParsing(true);
            const token = localStorage.getItem('token');
            const providedPat = githubAuthMode === 'pat' ? githubLinkToken.trim() : '';
            
            // First validate the connection using the working endpoint
            const validateResp = await fetch(API_ENDPOINTS.GIT_VALIDATE_CONNECTION, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    repo_url: githubLinkUrl,
                    pat: providedPat || null,
                    provider: 'github',
                })
            });
            
            const validateData = await validateResp.json();
            if (!validateResp.ok) {
                let errMessage = 'Failed to validate repository';
                if (validateData.detail) {
                    errMessage = Array.isArray(validateData.detail) ? validateData.detail.map(e => e.msg).join(', ') : validateData.detail;
                }
                throw new Error(errMessage);
            }

            // Now fetch the actual repo context
            const providedUsername = githubAuthMode === 'basic' ? String(githubLinkUsername || '').trim() : '';
            const providedPassword = githubAuthMode === 'basic' ? String(githubLinkPassword || '') : '';
            
            const resp = await fetch(API_ENDPOINTS.GITHUB_REPO_CONTEXT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    owner: validateData.owner,
                    repo: validateData.repo,
                    branch: 'main',
                    token: providedPat || null,
                    username: providedUsername || null,
                    password: providedPassword || null,
                })
            });
            
            const data = await resp.json();
            if (!resp.ok) {
                let errMessage = 'Failed to fetch repository context';
                if (data.detail) {
                    errMessage = Array.isArray(data.detail) ? data.detail.map(e => e.msg).join(', ') : data.detail;
                }
                throw new Error(errMessage);
            }

            const resolvedRepo = data.repo || `${validateData.owner}/${validateData.repo}`;
            const resolvedBranch = data.branch || 'main';
            const nextRepoContext = {
                repo: resolvedRepo,
                branch: resolvedBranch,
                context: data.context,
                fromLink: true,
                provider: 'github',
                url: validateData.normalized_url || `https://github.com/${resolvedRepo}.git`,
            };
            setRepoContext(nextRepoContext);
            persistRepoContextMetaForProject(nextRepoContext);
            saveRepoContextToStorage(nextRepoContext);
            if (githubAuthMode === 'basic') {
                setGithubLinkPassword('');
            }
            setGithubLinkError('');
        } catch (e) {
            setGithubLinkError(e.message || 'Failed to parse or load URL');
        } finally {
            setGithubLinkParsing(false);
        }
    };

    const handleRepoLinkUrlChange = (nextValue) => {
        const value = String(nextValue || '');
        const inferredProvider = inferRepoProviderFromUrl(value);
        const shouldSwitchToAzure = inferredProvider === 'azure-devops' && repoLinkProvider !== 'azure-devops';
        const shouldSwitchToGithub = inferredProvider === 'github' && repoLinkProvider !== 'github';

        if (shouldSwitchToAzure) {
            setRepoLinkProvider('azure-devops');
            setIsOAuthRepoSelected(false);
            setAzureLinkUrl(value);
            setGithubLinkError('');
        } else if (shouldSwitchToGithub) {
            setRepoLinkProvider('github');
            setGithubLinkUrl(value);
            setAzureLinkError('');
        } else if (repoLinkProvider === 'azure-devops') {
            setAzureLinkUrl(value);
        } else {
            setGithubLinkUrl(value);
        }

        if (repoContext) {
            setRepoContext(null);
            clearRepoContextFromStorage();
        }
    };

    const handleLoadAzureDevOpsUrl = async () => {
        setAzureLinkError('');
        setGithubLinkError('');

        const rawUrl = String(azureLinkUrl || '').trim();
        if (!rawUrl) {
            setAzureLinkError('Please enter an Azure DevOps repository URL.');
            return;
        }

        const pat = String(azureLinkToken || '').trim();

        if (!/dev\.azure\.com|\.visualstudio\.com/i.test(rawUrl)) {
            setAzureLinkError('Please enter a valid Azure DevOps URL (dev.azure.com or *.visualstudio.com).');
            return;
        }

        // Check if it's a project URL (without /_git/{repo})
        const isProjectUrl = (() => {
            if (rawUrl.includes('dev.azure.com')) {
                const urlParts = rawUrl.split('/').filter(Boolean);
                const gitIndex = urlParts.findIndex(part => part.toLowerCase() === '_git');
                // Project URL: dev.azure.com/{org}/{project} (exactly 2 parts after domain)
                // Repository URL: dev.azure.com/{org}/{project}/_git/{repo} (has _git)
                return gitIndex === -1 && urlParts.length >= 2;
            } else if (rawUrl.includes('.visualstudio.com')) {
                const urlParts = rawUrl.split('/').filter(Boolean);
                const gitIndex = urlParts.findIndex(part => part.toLowerCase() === '_git');
                return gitIndex === -1 && urlParts.length >= 1;
            }
            return false;
        })();

        if (isProjectUrl) {
            // It's a project URL - fetch repositories
            try {
                setAzureProjectReposLoading(true);
                setAzureLinkError('');
                const token = localStorage.getItem('token');

                // Parse organization and project from URL
                const urlObj = new URL(rawUrl.includes('://') ? rawUrl : `https://${rawUrl}`);
                const pathParts = urlObj.pathname.split('/').filter(Boolean);
                let organization = '';
                let project = '';

                if (urlObj.hostname.includes('dev.azure.com')) {
                    organization = decodeURIComponent(pathParts[0] || '');
                    project = decodeURIComponent(pathParts[1] || '');
                } else if (urlObj.hostname.includes('.visualstudio.com')) {
                    organization = urlObj.hostname.split('.visualstudio.com')[0];
                    project = decodeURIComponent(pathParts[0] || '');
                }

                if (!organization || !project) {
                    throw new Error('Unable to parse organization and project from URL.');
                }

                if (!selectedProjectKey) {
                    throw new Error('Please select a project first.');
                }

                const resp = await fetch(API_ENDPOINTS.AZURE_DEVOPS_LIST_PROJECT_REPOS, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        project_token: selectedProjectKey,
                        organization,
                        project,
                    }),
                });

                const data = await resp.json();
                if (!resp.ok) {
                    let errMessage = 'Failed to fetch repositories from Azure DevOps project';
                    if (data.detail) {
                        errMessage = Array.isArray(data.detail) ? data.detail.map((e) => e.msg).join(', ') : data.detail;
                    }
                    throw new Error(errMessage);
                }

                const repos = Array.isArray(data.repos) ? data.repos : [];
                if (repos.length === 0) {
                    setAzureLinkError('No repositories found in this project.');
                    return;
                }

                setAzureProjectRepos(repos);
                setAzureProjectUrl(rawUrl);
                setShowAzureRepoSelector(true);
            } catch (e) {
                setAzureLinkError(e.message || 'Failed to fetch repositories from Azure DevOps project');
            } finally {
                setAzureProjectReposLoading(false);
            }
            return;
        }

        // It's a repository URL - proceed with normal flow
        try {
            setAzureLinkParsing(true);
            const token = localStorage.getItem('token');
            const providedPat = azureLinkToken.trim();

            const resp = await fetch(API_ENDPOINTS.AZURE_DEVOPS_REPO_CONTEXT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({
                    repo_url: rawUrl,
                    token: providedPat || null,
                }),
            });
            const data = await resp.json();
            if (!resp.ok) {
                let errMessage = 'Failed to fetch Azure DevOps repository';
                if (data.detail) {
                    errMessage = Array.isArray(data.detail) ? data.detail.map((e) => e.msg).join(', ') : data.detail;
                }
                throw new Error(errMessage);
            }

            const nextRepoContext = {
                repo: data.repo,
                branch: data.branch,
                context: data.context,
                fromLink: true,
                provider: 'azure-devops',
                url: data.url || rawUrl,
            };
            setRepoContext(nextRepoContext);
            persistRepoContextMetaForProject(nextRepoContext);
            saveRepoContextToStorage(nextRepoContext);
            setAzureLinkError('');
        } catch (e) {
            setAzureLinkError(e.message || 'Failed to parse or load Azure DevOps URL');
        } finally {
            setAzureLinkParsing(false);
        }
    };

    const handleSelectAzureRepo = async (repo) => {
        const repoUrl = repo.repo_url || repo.html_url || `https://dev.azure.com/${repo.organization}/${repo.project}/_git/${repo.name}`;
        setAzureLinkUrl(repoUrl);
        setShowAzureRepoSelector(false);
        setAzureProjectRepos([]);
        // Automatically load the selected repository
        setTimeout(() => {
            handleLoadAzureDevOpsUrl();
        }, 100);
    };

    const handleNewAnalysis = () => {
        setProjectState(selectedProjectKey, {
            files: [],
            textInput: '',
            urlInput: '',
            urlRequirements: '',
            urlSource: '',
            urlFetchSummary: null,
            urlFetching: false,
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
        
        try {
            const reason = await customPrompt(
                `Provide a reason for creating a new revision for "${selectedProject.name}".`,
                'Create New Revision',
                '',
                'Enter revision reason...'
            );
            
            // Check if user cancelled or provided empty reason
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
                        const response = await fetch(API_ENDPOINTS.GOVERNANCE_REVISION_REASON(govId), {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                Authorization: `Bearer ${token}`
                            },
                            body: JSON.stringify({ reason: trimmedReason })
                        });
                        
                        if (!response.ok) {
                            throw new Error('Failed to save revision reason to backend');
                        }
                    }
                } catch (e) {
                    console.error("Failed to save revision reason to backend", e);
                    setError('Failed to save revision reason. Please try again.');
                    return;
                }
            }

            // Update the project state to unlock revision
            setProjectState(selectedProjectKey, {
                revisionReason: trimmedReason,
                revisionUnlocked: true,
                files: [],
                linkedFiles: [],
                textInput: '',
                urlInput: '',
                urlRequirements: '',
                urlSource: '',
                urlFetchSummary: null,
                urlFetching: false,
                result: null,
                error: ''
            });
            
            // Also refresh projects to ensure the UI is in sync
            if (refreshProjects) {
                await refreshProjects();
            }
            
            // Show success message
            await customAlert(
                'Revision unlocked successfully. You can now upload a new document.',
                'Success'
            );
        } catch (error) {
            console.error('Error in handleCreateRevision:', error);
            setError('Failed to create revision. Please try again.');
        }
    };

    const handleViewLatestProjectAnalysis = () => {
        if (!selectedProject?.latestDocument) return;
        // Navigate to the Agent Analysis page for this project
        navigate('/agent-analysis');
    };

    const goToGovernanceAssessment = () => {
        navigate(selectedProjectKey ? '/new-project/governance' : '/new-project');
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
                                    <div className="mt-1 text-sm text-app-status-error">{error}</div>
                                </div>
                                <button onClick={() => setError('')} className="ml-auto text-app-status-error hover:text-app-status-error">✕</button>
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
                                        <div className="rounded-xl border border-emerald-300/70 bg-app-status-successBg/90 p-4 shadow-sm shadow-emerald-900/20">
                                            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                                                <div>
                                                    <p className="text-sm font-semibold text-app-text-main">Selected Project</p>
                                                    <p className="text-xs text-app-text-label mt-1">
                                                        {selectedProject.name}
                                                        {selectedProject.classification && selectedProject.classification !== 'N/A' && (
                                                            <> • {selectedProject.classification}</>
                                                        )}
                                                        {selectedProject.weightedScore != null && selectedProject.weightedScore !== 'N/A' && (
                                                            <> • Score {selectedProject.weightedScore}/10</>
                                                        )}
                                                    </p>
                                                    <p className="text-xs text-app-text-label mt-1">
                                                        Status: {selectedProject.status === 'analysis_complete'
                                                            ? 'Analysis Complete (Locked)'
                                                            : selectedProject.status === 'screening_complete'
                                                                ? 'Requirement Screening Complete'
                                                                : 'Ready for Initial Upload'}
                                                    </p>
                                                    {isEnterpriseUploadBlocked && (
                                                        <p className="text-xs text-app-status-error mt-1">
                                                            Upload blocked: {getEnterpriseUploadBlockMessage()}
                                                        </p>
                                                    )}
                                                    {selectedProject.latestDocument && (
                                                        <p className="text-xs text-app-text-label mt-1">
                                                            Latest document: {selectedProject.latestDocument.filename} ({new Date(selectedProject.latestDocument.upload_date).toLocaleString('en-IN')})
                                                        </p>
                                                    )}
                                                </div>
                                                <div className="flex flex-col items-start sm:items-end gap-2">
                                                    {selectedProject.latestDocument && hasCompletedDocumentAnalysis(selectedProject.latestDocument) && (
                                                        <button
                                                            type="button"
                                                            onClick={handleViewLatestProjectAnalysis}
                                                            className="text-xs font-semibold text-app-status-success hover:text-app-status-success/80"
                                                        >
                                                            View Latest Analysis
                                                        </button>
                                                    )}
                                                    {selectedProject.documents.length > 0 && !revisionUnlocked && (
                                                        <button
                                                            type="button"
                                                            onClick={handleCreateRevision}
                                                            disabled={isEnterpriseUploadBlocked}
                                                            className="text-xs font-semibold text-app-primary-hover hover:text-app-primary-dark disabled:text-app-text-light disabled:cursor-not-allowed"
                                                        >
                                                            Create New Revision
                                                        </button>
                                                    )}
                                                </div>
                                            </div>
                                            {revisionUnlocked && (
                                                <div className="mt-3 rounded-lg border border-app-primary-ring/80 bg-app-primary-light/90 p-3">
                                                    <p className="text-xs font-semibold text-app-primary">Revision unlocked for this upload</p>
                                                    <p className="text-xs text-app-text-label mt-1">Reason: {revisionReason}</p>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="rounded-xl border border-amber-300/80 bg-app-status-warningBg/90 p-4">
                                            <p className="text-sm font-semibold text-app-status-warning">Select a project from the left panel to continue.</p>
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
                                            onClick={() => setActiveTab('url')}
                                            className={`pb-3 px-3 text-sm font-medium transition-colors relative ${activeTab === 'url' ? 'text-app-primary border-b-2 border-app-primary' : 'text-app-text-muted hover:text-app-text-label'}`}
                                            disabled={!selectedProject}
                                        >
                                            Upload URL
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setActiveTab('github-link')}
                                            className={`pb-3 px-3 text-sm font-medium transition-colors relative ${activeTab === 'github-link' ? 'text-app-primary border-b-2 border-app-primary' : 'text-app-text-muted hover:text-app-text-label'}`}
                                            disabled={!selectedProject}
                                        >
                                            Repositories
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setActiveTab('skills')}
                                            className={`pb-3 px-3 text-sm font-medium transition-colors relative ${activeTab === 'skills' ? 'text-app-primary border-b-2 border-app-primary' : 'text-app-text-muted hover:text-app-text-label'}`}
                                            disabled={!selectedProject}
                                        >
                                            Skills
                                        </button>
                                    </div>

                                    {activeTab === 'upload' ? (
                                        <div className={`border-2 border-dashed rounded-xl p-6 sm:p-10 text-center transition-colors bg-app-bg-page/50 group relative ${selectedProject && (selectedProject.documents.length === 0 || revisionUnlocked) && !isEnterpriseUploadBlocked ? 'border-app-border hover:border-blue-400 cursor-pointer' : 'border-app-border opacity-60'}`}>
                                            <input
                                                type="file"
                                                id={`file-upload-${activeTab}`}
                                                multiple
                                                onChange={handleFileChange}
                                                accept=".pdf,.docx,.pptx,.html,.htm,.png,.jpg,.jpeg,.txt"
                                                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                                                disabled={!selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked}
                                            />
                                            <div className="mx-auto w-12 h-12 text-app-text-light mb-3 group-hover:text-app-primary transition-colors">
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
                                                PDF, DOCX, PPTX, HTML, Images, Text
                                            </span>
                                        </div>
                                    ) : activeTab === 'linked-doc' ? (
                                        <div className={`border-2 border-dashed rounded-xl p-6 sm:p-10 text-center transition-colors bg-app-bg-page/50 group relative ${selectedProject && (selectedProject.documents.length === 0 || revisionUnlocked) && !isEnterpriseUploadBlocked ? 'border-app-border hover:border-blue-400 cursor-pointer' : 'border-app-border opacity-60'}`}>
                                            <input
                                                type="file"
                                                id={`file-upload-linked`}
                                                multiple
                                                onChange={handleFileChange}
                                                accept=".pdf,.docx,.pptx,.html,.htm,.png,.jpg,.jpeg,.txt"
                                                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                                                disabled={!selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked}
                                            />
                                            <div className="mx-auto w-12 h-12 text-app-text-light mb-3 group-hover:text-app-primary transition-colors">
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
                                                PDF, DOCX, PPTX, HTML, Images, Text
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
                                    ) : activeTab === 'url' ? (
                                        <div className="space-y-4">
                                            <div className="rounded-xl border border-app-border bg-app-bg-page/50 p-4">
                                                <label className="block text-sm font-semibold text-app-text-main mb-2">Website URL</label>
                                                <div className="flex flex-col sm:flex-row gap-2">
                                                    <input
                                                        type="url"
                                                        value={urlInput}
                                                        onChange={handleUrlInputChange}
                                                        placeholder="https://example.com/requirements"
                                                        className="flex-1 px-3 py-2.5 border border-app-border rounded-lg text-sm focus:ring-2 focus:ring-app-primary focus:border-app-primary outline-none transition-all bg-app-bg-card"
                                                        disabled={!selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked || urlFetching}
                                                    />
                                                    <button
                                                        type="button"
                                                        onClick={handleFetchUrlRequirements}
                                                        disabled={!urlInput.trim() || !selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked || urlFetching}
                                                        className="px-4 py-2.5 bg-app-text-main text-white text-sm font-semibold rounded-lg hover:bg-app-text-label disabled:opacity-50 transition-colors inline-flex items-center justify-center min-w-[136px]"
                                                    >
                                                        {urlFetching ? 'Fetching...' : 'Fetch URL'}
                                                    </button>
                                                </div>
                                                <p className="mt-2 text-xs text-app-text-muted">
                                                    Fetches webpage content and converts it into requirement text for analysis.
                                                </p>
                                            </div>
                                            <div className="rounded-xl border border-app-border bg-app-bg-card p-4">
                                                <div className="flex items-center justify-between gap-2 mb-2">
                                                    <h3 className="text-sm font-semibold text-app-text-main">Extracted Requirements</h3>
                                                    {urlSource && (
                                                        <span className="text-[11px] text-app-text-muted truncate max-w-[60%]" title={urlSource}>
                                                            Source: {urlSource}
                                                        </span>
                                                    )}
                                                </div>
                                                <textarea
                                                    value={urlRequirements}
                                                    onChange={(e) => setUrlRequirements(e.target.value)}
                                                    placeholder="Click 'Fetch URL' to generate requirement text from the webpage."
                                                    className="w-full min-h-64 max-h-[600px] p-4 border border-app-border rounded-xl focus:ring-2 focus:ring-app-primary focus:border-app-primary text-sm bg-app-bg-page/50 resize-y font-mono overflow-y-auto"
                                                    disabled={!selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked}
                                                />
                                                {urlFetchSummary && (
                                                    <div className="mt-2 text-xs text-app-text-muted">
                                                        Parsed headings: {urlFetchSummary.headings_found || 0}, paragraphs: {urlFetchSummary.paragraphs_found || 0}, list items: {urlFetchSummary.list_items_found || 0}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    ) : activeTab === 'skills' ? (
                                        <div className={`border-2 border-dashed rounded-xl p-6 sm:p-10 text-center transition-colors bg-app-bg-page/50 group relative ${selectedProject && (selectedProject.documents.length === 0 || revisionUnlocked) && !isEnterpriseUploadBlocked ? 'border-app-border hover:border-blue-400 cursor-pointer' : 'border-app-border opacity-60'}`}>
                                            <input
                                                type="file"
                                                id={`file-upload-skills`}
                                                multiple
                                                onChange={handleFileChange}
                                                accept=".md,.txt"
                                                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                                                disabled={!selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked}
                                            />
                                            <div className="mx-auto w-12 h-12 text-app-text-light mb-3 group-hover:text-app-primary transition-colors">
                                                <FileText className="w-12 h-12" />
                                            </div>
                                            <span className="mt-2 block text-sm font-medium text-app-text-main">
                                                {skillFiles.length > 0
                                                    ? `${skillFiles.length} skill file(s) selected`
                                                    : "Click to select skill files (max 100MB total)"}
                                            </span>
                                            {skillFiles.length > 0 && (
                                                <div className="mt-2 text-xs text-app-text-muted flex flex-col items-center">
                                                    {skillFiles.map((f, i) => (
                                                        <span key={i} className="truncate max-w-[200px]">{f.name}</span>
                                                    ))}
                                                </div>
                                            )}
                                            <span className="mt-1 block text-xs text-app-text-light">
                                                Markdown (.md) and Text (.txt) files only
                                            </span>
                                            <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg text-left">
                                                <p className="text-xs text-blue-900 font-semibold mb-1">💡 What are Skills?</p>
                                                <p className="text-xs text-blue-700">
                                                    Skills are additional context files (guides, documentation, best practices) that help the AI understand your project better and provide more accurate analysis.
                                                </p>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="space-y-6">
                                            {/* Repository Context Viewer - Show when repo is loaded */}
                                            {repoContext?.context && (
                                                <div className="bg-gradient-to-br from-emerald-50 to-teal-50 dark:from-emerald-900/20 dark:to-teal-900/20 border-2 border-emerald-200 dark:border-emerald-800 rounded-xl p-6 shadow-lg">
                                                    <div className="flex items-start justify-between gap-4 mb-4">
                                                        <div className="flex items-start gap-3 flex-1">
                                                            <div className="w-10 h-10 rounded-lg bg-emerald-500 flex items-center justify-center flex-shrink-0">
                                                                <CheckCircle2 className="w-6 h-6 text-white" />
                                                            </div>
                                                            <div className="flex-1 min-w-0">
                                                                <h3 className="text-lg font-bold text-emerald-900 dark:text-dark-100 mb-1">
                                                                    Repository Loaded Successfully
                                                                </h3>
                                                                <p className="text-sm text-emerald-700 dark:text-dark-300 font-mono truncate">
                                                                    {repoContext.repo} {repoContext.branch && `(${repoContext.branch})`}
                                                                </p>
                                                                <p className="text-xs text-emerald-600 dark:text-dark-400 mt-1">
                                                                    Provider: {repoContext.provider === 'azure-devops' ? 'Azure DevOps' : 'GitHub'}
                                                                </p>
                                                            </div>
                                                        </div>
                                                        <button
                                                            type="button"
                                                            onClick={() => {
                                                                setRepoContext(null);
                                                                clearRepoContextFromStorage();
                                                                setIsOAuthRepoSelected(false);
                                                            }}
                                                            className="px-3 py-1.5 text-xs font-semibold text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                                                        >
                                                            Clear
                                                        </button>
                                                    </div>
                                                    
                                                    {/* Repository Context Preview */}
                                                    <div className="bg-white dark:bg-gray-900 rounded-lg border border-emerald-200 dark:border-emerald-800 p-4 max-h-96 overflow-y-auto">
                                                        <div className="flex items-center justify-between mb-3">
                                                            <h4 className="text-sm font-bold text-gray-900 dark:text-gray-100">Repository Structure</h4>
                                                            <span className="text-xs text-gray-500 dark:text-gray-400">
                                                                {repoContext.context.split('\n').filter(line => line.trim().startsWith('src/') || line.trim().startsWith('public/') || line.trim().includes('.')).length} files detected
                                                            </span>
                                                        </div>
                                                        <pre className="text-xs font-mono text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words">
                                                            {repoContext.context.substring(0, 2000)}{repoContext.context.length > 2000 && '...\n\n[Content truncated for preview]'}
                                                        </pre>
                                                    </div>
                                                    
                                                    <div className="mt-4 flex items-center gap-2 text-xs text-emerald-700 dark:text-dark-300">
                                                        <Info className="w-4 h-4" />
                                                        <span>This repository context will be sent to AI for analysis and planning.</span>
                                                    </div>
                                                </div>
                                            )}
                                            
                                            {/* Repository Configuration */}
                                            <div className="max-w-3xl mx-auto">
                                                <div className="border border-app-border rounded-xl bg-app-bg-card shadow-sm p-6">
                                                    <div className="mb-4">
                                                        <h3 className="text-base font-bold text-app-text-main mb-2">Repository Configuration</h3>
                                                        <p className="text-xs text-app-text-muted">
                                                            Provide a repository link from GitHub or Azure DevOps. For private repositories, use PAT.
                                                        </p>
                                                    </div>
                                                
                                                {/* Show saved credentials indicator - Only show for the saved provider */}
                                                {credentialsLocked && repoLinkProvider === 'azure-devops' && azureLinkUrl && (
                                                    <div className="mb-4 p-3 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-blue-200 dark:border-blue-800 rounded-lg shadow-sm">
                                                        <div className="flex items-start justify-between gap-2">
                                                            <div className="flex items-start gap-2 flex-1 min-w-0">
                                                                <CheckCircle2 className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                                                                <div className="flex-1 min-w-0">
                                                                    <p className="text-xs font-bold text-blue-900 dark:text-blue-100 uppercase tracking-wide mb-1">
                                                                        <span className="flex items-center gap-1.5">
                                                                            <AzureDevOpsIcon className="w-3.5 h-3.5" />
                                                                            Azure DevOps Credentials Saved
                                                                        </span>
                                                                    </p>
                                                                    {hasChangedCredentials ? (
                                                                        <div className="mt-2 inline-flex items-center gap-1.5 px-2 py-1 bg-amber-100 dark:bg-amber-900/30 rounded-md">
                                                                            <AlertTriangle className="w-3 h-3 text-amber-600 dark:text-amber-400" />
                                                                            <span className="text-[10px] font-semibold text-amber-800 dark:text-amber-200">
                                                                                Changed once - Contact support for further changes
                                                                            </span>
                                                                        </div>
                                                                    ) : (
                                                                        <button
                                                                            type="button"
                                                                            onClick={handleChangeCredentials}
                                                                            className="mt-2 text-[11px] font-semibold text-blue-700 dark:text-blue-300 hover:text-blue-900 dark:hover:text-blue-100 underline underline-offset-2 decoration-2 hover:decoration-blue-500 transition-all flex items-center gap-1"
                                                                        >
                                                                            <RefreshCw className="w-3 h-3" />
                                                                            Change credentials (one-time only)
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}
                                                
                                                {credentialsLocked && repoLinkProvider === 'github' && githubLinkUrl && (
                                                    <div className="mb-4 p-3 bg-gradient-to-r from-gray-50 to-slate-50 dark:from-gray-900/20 dark:to-slate-900/20 border border-gray-200 dark:border-gray-800 rounded-lg shadow-sm">
                                                        <div className="flex items-start justify-between gap-2">
                                                            <div className="flex items-start gap-2 flex-1 min-w-0">
                                                                <CheckCircle2 className="w-5 h-5 text-app-status-success flex-shrink-0 mt-0.5" />
                                                                <div className="flex-1 min-w-0">
                                                                    <p className="text-xs font-bold text-app-text-main uppercase tracking-wide mb-1">
                                                                        <span className="flex items-center gap-1.5">
                                                                            <GitHubIcon className="w-3.5 h-3.5" />
                                                                            GitHub Credentials Saved
                                                                        </span>
                                                                    </p>
                                                                    <p className="text-[11px] text-app-text-muted font-mono truncate" title={githubLinkUrl}>
                                                                        {githubLinkUrl}
                                                                    </p>
                                                                    {hasChangedCredentials ? (
                                                                        <div className="mt-2 inline-flex items-center gap-1.5 px-2 py-1 bg-amber-100 dark:bg-amber-900/30 rounded-md">
                                                                            <AlertTriangle className="w-3 h-3 text-amber-600 dark:text-amber-400" />
                                                                            <span className="text-[10px] font-semibold text-amber-800 dark:text-amber-200">
                                                                                Changed once - Contact support for further changes
                                                                            </span>
                                                                        </div>
                                                                    ) : (
                                                                        <button
                                                                            type="button"
                                                                            onClick={handleChangeCredentials}
                                                                            className="mt-2 text-[11px] font-semibold text-app-primary hover:text-app-primary-hover underline underline-offset-2 decoration-2 hover:decoration-app-primary transition-all flex items-center gap-1"
                                                                        >
                                                                            <RefreshCw className="w-3 h-3" />
                                                                            Change credentials (one-time only)
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}
                                                
                                                <div className="mb-3 inline-flex rounded-lg border border-app-border p-1 bg-app-bg-page/60">
                                                    <button
                                                        type="button"
                                                        onClick={() => { setRepoLinkProvider('github'); setAzureLinkError(''); }}
                                                        className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${repoLinkProvider === 'github' ? 'bg-app-primary text-white' : 'text-app-text-muted hover:text-app-text-label'}`}
                                                    >
                                                        <span className="flex items-center gap-1">
                                                            <GitHubIcon className="w-4 h-4" />
                                                            <span>GitHub</span>
                                                        </span>
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => { setRepoLinkProvider('azure-devops'); setGithubLinkError(''); setIsOAuthRepoSelected(false); }}
                                                        className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${repoLinkProvider === 'azure-devops' ? 'bg-app-primary text-white' : 'text-app-text-muted hover:text-app-text-label'}`}
                                                    >
                                                        <span className="flex items-center gap-1">
                                                            <AzureDevOpsIcon className="w-4 h-4" />
                                                            <span>Azure DevOps</span>
                                                        </span>
                                                    </button>
                                                </div>
                                                
                                                {repoLinkProvider === 'github' && (
                                                    <div className="mb-3 inline-flex rounded-lg border border-app-border p-1 bg-app-bg-page/60">
                                                        <button
                                                            type="button"
                                                            onClick={() => { setGithubAuthMode('pat'); setGithubLinkError(''); }}
                                                            className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${githubAuthMode === 'pat' ? 'bg-app-primary text-white' : 'text-app-text-muted hover:text-app-text-label'}`}
                                                        >
                                                            Use PAT
                                                        </button>
                                                        <button
                                                            type="button"
                                                            onClick={() => { setGithubAuthMode('basic'); setGithubLinkError(''); }}
                                                            className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${githubAuthMode === 'basic' ? 'bg-app-primary text-white' : 'text-app-text-muted hover:text-app-text-label'}`}
                                                        >
                                                            Username + Password
                                                        </button>
                                                    </div>
                                                )}
                                                <div className="flex flex-col gap-3 mt-auto">
                                                    <input
                                                        type="text"
                                                        value={repoLinkProvider === 'azure-devops' ? azureLinkUrl : githubLinkUrl}
                                                        onChange={e => handleRepoLinkUrlChange(e.target.value)}
                                                        placeholder={repoLinkProvider === 'azure-devops' ? 'https://dev.azure.com/org/project/_git/repo or https://dev.azure.com/org/project' : 'https://github.com/owner/repo'}
                                                        className="w-full px-3 py-2.5 border border-app-border rounded-lg text-sm focus:ring-2 focus:ring-app-primary focus:border-app-primary outline-none transition-all bg-app-bg-page/50"
                                                    />
                                                    {repoLinkProvider === 'azure-devops' ? (
                                                        <input
                                                            type="password"
                                                            value={azureLinkToken}
                                                            onChange={e => {
                                                                setAzureLinkToken(e.target.value);
                                                                if (repoContext) { setRepoContext(null); clearRepoContextFromStorage(); }
                                                            }}
                                                            placeholder="Azure DevOps PAT"
                                                            className="w-full px-3 py-2.5 border border-app-border rounded-lg text-sm focus:ring-2 focus:ring-app-primary focus:border-app-primary outline-none transition-all bg-app-bg-page/50"
                                                        />
                                                    ) : githubAuthMode === 'pat' ? (
                                                        <input
                                                            type="password"
                                                            value={githubLinkToken}
                                                            onChange={e => {
                                                                setGithubLinkToken(e.target.value);
                                                                if (repoContext) { setRepoContext(null); clearRepoContextFromStorage(); }
                                                            }}
                                                            placeholder="GitHub PAT"
                                                            className="w-full px-3 py-2.5 border border-app-border rounded-lg text-sm focus:ring-2 focus:ring-app-primary focus:border-app-primary outline-none transition-all bg-app-bg-page/50"
                                                        />
                                                    ) : (
                                                        <>
                                                            <input
                                                                type="text"
                                                                value={githubLinkUsername}
                                                                onChange={e => {
                                                                    setGithubLinkUsername(e.target.value);
                                                                    if (repoContext) { setRepoContext(null); clearRepoContextFromStorage(); }
                                                                }}
                                                                placeholder="GitHub username"
                                                                className="w-full px-3 py-2.5 border border-app-border rounded-lg text-sm focus:ring-2 focus:ring-app-primary focus:border-app-primary outline-none transition-all bg-app-bg-page/50"
                                                            />
                                                            <input
                                                                type="password"
                                                                value={githubLinkPassword}
                                                                onChange={e => {
                                                                    setGithubLinkPassword(e.target.value);
                                                                    if (repoContext) { setRepoContext(null); clearRepoContextFromStorage(); }
                                                                }}
                                                                placeholder="GitHub password"
                                                                className="w-full px-3 py-2.5 border border-app-border rounded-lg text-sm focus:ring-2 focus:ring-app-primary focus:border-app-primary outline-none transition-all bg-app-bg-page/50"
                                                            />
                                                        </>
                                                    )}
                                                    <div className="flex items-center gap-2">
                                                        <button
                                                            type="button"
                                                            onClick={repoLinkProvider === 'azure-devops' ? handleLoadAzureDevOpsUrl : handleLoadGithubUrl}
                                                            disabled={repoLinkProvider === 'azure-devops'
                                                                ? (!azureLinkUrl || azureLinkParsing || azureProjectReposLoading)
                                                                : (!githubLinkUrl || githubLinkParsing)}
                                                            className="flex-1 px-4 py-2 bg-app-text-main text-white text-sm font-semibold rounded-lg hover:bg-app-text-label disabled:opacity-50 transition-colors inline-flex items-center justify-center h-10 shadow-sm"
                                                        >
                                                            {(repoLinkProvider === 'azure-devops' ? (azureLinkParsing || azureProjectReposLoading) : githubLinkParsing) ? (
                                                                <><span className="animate-spin w-3.5 h-3.5 border-2 border-app-bg-card border-t-transparent rounded-full mr-2"></span> Loading...</>
                                                            ) : 'Load Repository'}
                                                        </button>
                                                        {repoContext && repoContext.fromLink && (
                                                            <button
                                                                onClick={() => {
                                                                    setRepoContext(null);
                                                                    clearRepoContextFromStorage();
                                                                    setGithubLinkUrl('');
                                                                    setGithubLinkToken('');
                                                                    setGithubAuthMode('pat');
                                                                    setGithubLinkUsername('');
                                                                    setGithubLinkPassword('');
                                                                    setGithubLinkError('');
                                                                    setAzureLinkUrl('');
                                                                    setAzureLinkToken('');
                                                                    setAzureLinkBranch('');
                                                                    setAzureLinkError('');
                                                                }}
                                                                className="px-3 py-2 border border-red-200 text-app-status-error bg-app-status-errorBg rounded-lg hover:bg-app-status-errorBg text-sm font-semibold h-10 transition-colors"
                                                                title="Clear repository"
                                                            >
                                                                Clear
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>

                                                {repoLinkProvider === 'azure-devops'
                                                    ? (azureLinkError && <p className="text-app-status-error text-[11px] font-medium mt-3 bg-app-status-errorBg p-2.5 rounded border border-app-status-errorBg">{azureLinkError}</p>)
                                                    : (githubLinkError && <p className="text-app-status-error text-[11px] font-medium mt-3 bg-app-status-errorBg p-2.5 rounded border border-app-status-errorBg">{githubLinkError}</p>)}
                                                {showAzureRepoSelector && azureProjectRepos.length > 0 && (
                                                    <div className="mt-3 border border-app-border rounded-lg bg-app-bg-page/50 p-3 max-h-64 overflow-y-auto">
                                                        <p className="text-xs font-semibold text-app-text-main mb-2">Select a repository:</p>
                                                        <div className="space-y-1.5">
                                                            {azureProjectRepos.map((repo) => (
                                                                <button
                                                                    key={repo.id || repo.name}
                                                                    type="button"
                                                                    onClick={() => handleSelectAzureRepo(repo)}
                                                                    className="w-full text-left px-3 py-2 rounded-md border border-app-border bg-app-bg-card hover:bg-app-bg-hover hover:border-app-primary transition-colors text-xs"
                                                                >
                                                                    <div className="font-semibold text-app-text-main">{repo.name}</div>
                                                                    {repo.description && (
                                                                        <div className="text-app-text-muted mt-0.5 truncate">{repo.description}</div>
                                                                    )}
                                                                    {repo.default_branch && (
                                                                        <div className="text-app-text-muted mt-0.5 text-[10px]">Default branch: {repo.default_branch}</div>
                                                                    )}
                                                                </button>
                                                            ))}
                                                        </div>
                                                        <button
                                                            type="button"
                                                            onClick={() => {
                                                                setShowAzureRepoSelector(false);
                                                                setAzureProjectRepos([]);
                                                                setAzureProjectUrl('');
                                                            }}
                                                            className="mt-2 text-xs text-app-text-muted hover:text-app-text-label"
                                                        >
                                                            Cancel
                                                        </button>
                                                    </div>
                                                )}
                                                {repoContext && repoContext.fromLink && (
                                                    <div className="mt-3 p-2.5 bg-app-status-successBg border border-emerald-200 rounded text-emerald-800 shadow-sm flex items-center text-xs font-semibold">
                                                        <CheckCircle2 className="w-4 h-4 mr-1.5 flex-shrink-0 text-app-status-success" />
                                                        <span className="truncate">Loaded: {repoContext.repo} {repoContext.branch ? `(${repoContext.branch})` : ''}</span>
                                                    </div>
                                                )}
                                            </div>
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
                                            <p className="text-sm font-medium text-app-status-error">{error}</p>
                                        </div>
                                    )}

                                    <div className="flex justify-end gap-3 pt-6">
                                        <button
                                            type="submit"
                                            disabled={!selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked || (files.length === 0 && linkedFiles.length === 0 && !textInput.trim() && !urlInput.trim() && !urlRequirements.trim() && !repoContext?.context && skillFiles.length === 0) || processing || urlFetching}
                                            className={`inline-flex items-center justify-center py-3 px-6 text-sm font-semibold rounded-lg text-white transition-all transform active:scale-95 shadow-md ${!selectedProject || (selectedProject.documents.length > 0 && !revisionUnlocked) || isEnterpriseUploadBlocked || (files.length === 0 && linkedFiles.length === 0 && !textInput.trim() && !urlInput.trim() && !urlRequirements.trim() && !repoContext?.context && skillFiles.length === 0) || processing || urlFetching
                                                ? 'bg-app-border cursor-not-allowed shadow-none'
                                                : 'bg-app-primary hover:bg-app-primary-hover hover:-translate-y-0.5 hover:shadow-lg'
                                                }`}
                                        >
                                            <Zap className={`w-4 h-4 mr-2 ${processing ? 'animate-pulse' : ''}`} />
                                            {processing
                                                ? (hasGovernanceAssessment ? 'Analyzing...' : 'Saving Screening...')
                                                : selectedProject?.documents.length > 0
                                                    ? (hasGovernanceAssessment ? 'Start Revision Analysis' : 'Continue to Governance')
                                                    : (hasGovernanceAssessment ? 'Start Analysis' : 'Complete Requirement Screening')}
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
                                        <div className="hidden sm:block h-4 w-px bg-app-border"></div>
                                        <button
                                            onClick={handleNewAnalysis}
                                            className="text-sm text-app-primary hover:text-app-primary-dark font-medium hover:underline flex items-center"
                                        >
                                            <Plus className="w-4 h-4 mr-1" /> Analyze Another
                                        </button>
                                    </div>
                                </div>

                                {hasGovernanceAssessment ? (
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
                                ) : (
                                    <div className="bg-gradient-to-r from-sky-50 to-app-primary-light rounded-xl shadow-sm border border-sky-200/70 p-5 flex flex-col sm:flex-row items-center justify-between gap-4">
                                        <div className="flex items-center gap-3">
                                            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-sky-500 to-app-primary flex items-center justify-center shadow-lg shadow-sky-200">
                                                <CheckCircle2 className="w-5 h-5 text-white" />
                                            </div>
                                            <div>
                                                <h3 className="text-sm font-bold text-sky-950">Governance Assessment</h3>
                                                <p className="text-xs text-sky-800">Requirement Screening is complete. Finish Governance next, then continue through Agent Analysis and prerequisites.</p>
                                            </div>
                                        </div>
                                        <button
                                            onClick={goToGovernanceAssessment}
                                            className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-bold text-white bg-gradient-to-r from-sky-600 to-app-primary rounded-lg shadow-lg shadow-sky-500/25 hover:shadow-sky-500/40 hover:-translate-y-0.5 transition-all active:scale-95 flex-shrink-0"
                                        >
                                            <CheckCircle2 className="w-4 h-4" />
                                            Complete Governance
                                        </button>
                                    </div>
                                )}

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
                                                    { label: 'Timeline (For Developer Only Mode)', value: metrics?.timeline || 'TBD', icon: Clock, color: 'text-app-status-success', bg: 'bg-app-status-successBg' }
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
                                                <h3 className="text-base font-bold text-app-text-main mb-4 pb-2 border-b border-app-border-light">
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
                                                    <div className="mt-4 pt-4 border-t border-app-bg-page">
                                                        {(() => {
                                                            // Check if we have structured sections or need to parse from markdown
                                                            const sections = result.extraction?.sections;
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
                </main>
            )}
        </>
    );
};

export default Dashboard;
