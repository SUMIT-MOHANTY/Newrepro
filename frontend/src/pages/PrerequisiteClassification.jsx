import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_ENDPOINTS, VIBE_WORKSPACE_URL, API_BASE_URL } from '../config';
import {
    KeyRound, CheckCircle2, Circle, AlertCircle, AlertTriangle, ArrowRight,
    ChevronLeft, Database, Globe, Server,
    Lock, FileKey, Cloud, Package, Info, Sparkles, Loader2,
    Trash2, FolderGit2, FileCode, Sliders, RefreshCw
} from 'lucide-react';

import { getCachedTaskToken, setCachedTaskToken as cacheTaskToken } from '../utils/tokenCache';
import { upsertDraftProject } from '../utils/draftProjects';
import { sanitizeErrorMessage } from '../utils/errorHandling';

/* ─────────────────────────────────────────────────────────
   CATEGORY CONFIG — icon + colour for each prerequisite type
───────────────────────────────────────────────────────── */
const CATEGORY_CONFIG = {
    credentials: {
        icon: Lock,
        label: 'Credentials & Access Keys',
        gradient: 'from-app-status-warning to-orange-600',
        bg: 'bg-app-status-warningBg/30 dark:bg-app-status-warningBg/10',
        border: 'border-amber-200 dark:border-amber-900/50',
        text: 'text-app-status-warning dark:text-amber-400',
        badge: 'bg-app-status-warningBg text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
    },
    apis: {
        icon: Globe,
        label: 'APIs & Integrations',
        gradient: 'from-app-primary to-app-primary',
        bg: 'bg-app-primary-light/50 dark:bg-app-primary-light/10',
        border: 'border-app-primary-ring dark:border-app-primary-ring/30',
        text: 'text-app-primary-hover dark:text-blue-400',
        badge: 'bg-app-primary-light text-app-primary-dark dark:bg-blue-900/50 dark:text-blue-200',
    },
    infrastructure: {
        icon: Server,
        label: 'Infrastructure & Services',
        gradient: 'from-app-status-success to-teal-600',
        bg: 'bg-app-status-successBg/30 dark:bg-app-status-successBg/10',
        border: 'border-emerald-200 dark:border-emerald-900/50',
        text: 'text-app-status-success dark:text-emerald-400',
        badge: 'bg-app-status-successBg text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300',
    },
    databases: {
        icon: Database,
        label: 'Databases & Storage',
        gradient: 'from-violet-500 to-purple-600',
        bg: 'bg-violet-50 dark:bg-violet-900/20',
        border: 'border-violet-200 dark:border-violet-800/50',
        text: 'text-violet-700 dark:text-violet-400',
        badge: 'bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200',
    },
    cloud: {
        icon: Cloud,
        label: 'Cloud Services',
        gradient: 'from-sky-500 to-cyan-600',
        bg: 'bg-sky-50 dark:bg-sky-900/20',
        border: 'border-sky-200 dark:border-sky-800/50',
        text: 'text-sky-700 dark:text-sky-400',
        badge: 'bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200',
    },
    dependencies: {
        icon: Package,
        label: 'Dependencies & Libraries',
        gradient: 'from-app-status-error to-pink-600',
        bg: 'bg-app-status-errorBg/30 dark:bg-app-status-errorBg/10',
        border: 'border-rose-200 dark:border-rose-900/50',
        text: 'text-app-status-error dark:text-rose-400',
        badge: 'bg-app-status-errorBg text-rose-800 dark:bg-rose-900/50 dark:text-rose-300',
    },
    other: {
        icon: FileKey,
        label: 'Other Prerequisites',
        gradient: 'from-app-text-muted to-app-text-label',
        bg: 'bg-app-bg-page dark:bg-slate-800/50',
        border: 'border-app-border dark:border-slate-700',
        text: 'text-app-text-label dark:text-slate-300',
        badge: 'bg-app-bg-muted text-app-text-main dark:bg-slate-700 dark:text-slate-200',
    },
};

/* ─────────────────────────────────────────────────────────
   PROCESS MODE CONFIG
───────────────────────────────────────────────────────── */
const PROCESS_MODE_STORAGE_KEY = 'status_dashboard_process_mode_map';

function readProcessModeMap() {
    try {
        const raw = localStorage.getItem(PROCESS_MODE_STORAGE_KEY);
        if (!raw) return {};
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
        return {};
    }
}

function writeProcessModeMap(map) {
    try {
        localStorage.setItem(PROCESS_MODE_STORAGE_KEY, JSON.stringify(map));
    } catch {
        // Ignore errors
    }
}

function saveProcessModeForProject(projectKey, mode) {
    if (!projectKey || !mode) return;
    const map = readProcessModeMap();
    map[projectKey] = mode;
    writeProcessModeMap(map);
}

const PROCESS_MODE_OPTIONS = [
    {
        id: 'developer_only',
        title: 'Developer Only',
        description: 'Open Status Dashboard without showing AI agents.',
        enabled: true,
    },
    {
        id: 'ai_assist',
        title: 'AI Assist',
        description: 'Redirect to VibeCoding with AI assistance for guided development.',
        enabled: true,
    },
    {
        id: 'vibe_coding',
        title: 'Vibe Coding',
        description: 'Open VibeCoding workspace with BRD. Auto-creates project, tasks, and executes code.',
        enabled: true,
    },
    {
        id: 'coexistence',
        title: 'Coexistence',
        description: 'Open Status Dashboard with agents available for manual run.',
        enabled: true,
    },
    {
        id: 'ai_first',
        title: 'AI-First Mode',
        description: 'Open Status Dashboard and auto-start all agents.',
        enabled: true,
    },
];

/* ─────────────────────────────────────────────────────────
   AI PREREQUISITE EXTRACTION — parses the analysis report
───────────────────────────────────────────────────────── */
const inferFieldTypeFromRequirement = (name = '', description = '') => {
    const lower = `${name} ${description}`.toLowerCase();
    if (
        /\b(pdf|docx?|xlsx?|pptx?|txt|md|png|jpe?g|webp|gif|image|screenshot|diagram|attachment|document|file|upload)\b/.test(lower)
    ) {
        return 'file';
    }
    if (/\burl\b|\blink\b|\bwebsite\b|\bendpoint\b|\buri\b/.test(lower)) {
        return 'url';
    }
    return 'text';
};

const extractPrerequisitesFromAnalysis = (analysisData) => {
    if (!analysisData) return [];

    // Helper: strip HTML tags and clean up whitespace
    const stripHtml = (html) => {
        if (!html) return '';
        return html
            .replace(/<br\s*\/?>/gi, ' ')           // <br> → space
            .replace(/<\/(?:li|p|div|tr|h\d)>/gi, '. ')  // closing block tags → period
            .replace(/<[^>]*>/g, '')                  // strip all remaining tags
            .replace(/&amp;/g, '&')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>')
            .replace(/&quot;/g, '"')
            .replace(/&#39;/g, "'")
            .replace(/\s{2,}/g, ' ')                  // collapse whitespace
            .replace(/\.\s*\./g, '.')                  // collapse double periods
            .trim();
    };

    const items = [];
    let id = 1;

    // PRIORITY 1: Check for structured prerequisites from chunked analysis stages
    if (analysisData.stages?.stage4_implementation?.prerequisites && Array.isArray(analysisData.stages.stage4_implementation.prerequisites)) {
        console.log('Found structured prerequisites from stage4_implementation:', analysisData.stages.stage4_implementation.prerequisites);
        return analysisData.stages.stage4_implementation.prerequisites.map((p, idx) => {
            if (typeof p === 'string') {
                const cleanString = stripHtml(p);
                return {
                    id: idx + 1,
                    name: cleanString || `Prerequisite ${idx + 1}`,
                    description: '', 
                    category: 'other',
                    priority: 'medium',
                    fieldType: inferFieldTypeFromRequirement(cleanString, ''),
                    provided: false,
                    containsSecret: false,
                    userValue: '',
                    userFileName: '',
                };
            }

            // Handle structured prerequisite objects
            const name = stripHtml(p.name || p.title || `Prerequisite ${idx + 1}`);
            const description = stripHtml(p.description || p.details || '');
            const fieldType = inferFieldTypeFromRequirement(name, description);
            return {
                id: idx + 1,
                name,
                description,
                category: p.category || 'other',
                priority: p.priority || 'medium',
                fieldType,
                provided: false,
                containsSecret: false,
                userValue: '',
                userFileName: '',
            };
        });
    }

    // PRIORITY 2: Check for prerequisites in the main analysis object
    if (analysisData.prerequisites && Array.isArray(analysisData.prerequisites)) {
        console.log('Found prerequisites in main analysis:', analysisData.prerequisites);
        return analysisData.prerequisites.map((p, idx) => {
            // ==========================================
            // FIX START: Handle string inputs
            // ==========================================
            if (typeof p === 'string') {
                const cleanString = stripHtml(p);
                return {
                    id: idx + 1,
                    name: cleanString || `Prerequisite ${idx + 1}`,
                    description: '', // Strings don't have descriptions by default
                    category: 'other',
                    priority: 'medium',
                    fieldType: inferFieldTypeFromRequirement(cleanString, ''),
                    provided: false,
                    containsSecret: false,
                    userValue: '',
                    userFileName: '',
                };
            }
            // ==========================================
            // FIX END
            // ==========================================

            // Existing logic for Objects
            const name = stripHtml(p.name || p.title || `Prerequisite ${idx + 1}`);
            const description = stripHtml(p.description || p.details || '');
            const fieldType = inferFieldTypeFromRequirement(name, description);
            return {
                id: idx + 1,
                name,
                description,
                category: p.category || 'other',
                priority: p.priority || 'medium',
                fieldType,
                provided: false,
                containsSecret: false,
                userValue: '',
                userFileName: '',
            };
        });
    }

    // Smart extraction from analysis text (Fallback if structure is missing)
    const rawText = typeof analysisData === 'string'
        ? analysisData
        : (analysisData.analysis || analysisData.report || JSON.stringify(analysisData));

    // Strip HTML from the analysis text BEFORE pattern matching
    const analysisText = stripHtml(rawText);

    // Pattern-based extraction
    const patterns = [
        // Credentials & API keys
        { regex: /(?:api[- ]?key|access[- ]?key|secret[- ]?key|auth(?:entication)?[- ]?token|oauth|jwt|bearer)/gi, category: 'credentials', label: 'API Key / Authentication Token' },
        { regex: /(?:database|db)[- ]?(?:connection|credentials?|password|url|string)/gi, category: 'databases', label: 'Database Credentials' },
        { regex: /(?:cloud)[- ]?(?:credentials?|account|subscription|key)/gi, category: 'cloud', label: 'Cloud Service Credentials' },
        { regex: /(?:smtp|email)[- ]?(?:server|credentials?|config)/gi, category: 'infrastructure', label: 'Email/SMTP Configuration' },
        { regex: /(?:ssl|tls)[- ]?(?:certificate|cert)/gi, category: 'credentials', label: 'SSL/TLS Certificate' },
        { regex: /(?:ssh)[- ]?(?:key|access)/gi, category: 'credentials', label: 'SSH Key Access' },
        { regex: /(?:domain|dns)[- ]?(?:name|config|registration)/gi, category: 'infrastructure', label: 'Domain / DNS Configuration' },
        { regex: /(?:compute)/gi, category: 'infrastructure', label: 'Deployment Platform' },
        { regex: /(?:ci[/ ]cd|jenkins|github[- ]?actions|gitlab[- ]?ci|pipeline)/gi, category: 'infrastructure', label: 'CI/CD Pipeline Access' },
        { regex: /(?:cache[- ]?server)/gi, category: 'databases', label: 'Cache Server (Redis/Memcache)' },
        { regex: /(?:storage[- ]?storage|object[- ]?storage|file[- ]?storage)/gi, category: 'cloud', label: 'Object / File Storage Service' },
        { regex: /(?:message[- ]?queue|rabbitmq|kafka|sqs)/gi, category: 'infrastructure', label: 'Message Queue Service' },
        { regex: /(?:third[- ]?party|external)[- ]?(?:api|service|integration)/gi, category: 'apis', label: 'Third-Party API Integration' },
        { regex: /(?:payment|stripe|paypal)[- ]?(?:gateway|integration|key)/gi, category: 'apis', label: 'Payment Gateway Credentials' },
        { regex: /(?:cdn|cloudflare|cloudfront)/gi, category: 'cloud', label: 'CDN Configuration' },
        { regex: /(?:monitoring|logging|elk|datadog|newrelic)/gi, category: 'infrastructure', label: 'Monitoring & Logging Service' },
        { regex: /(?:npm|pip|maven|gradle|nuget)[- ]?(?:registry|repository|private)/gi, category: 'dependencies', label: 'Private Package Registry Access' },
        { regex: /(?:ldap|active[- ]?directory|sso|saml)/gi, category: 'credentials', label: 'SSO / Directory Service Access' },
        { regex: /(?:webhook|callback[- ]?url)/gi, category: 'apis', label: 'Webhook / Callback URL' },
        { regex: /(?:firewall|security[- ]?group|vpc|network)/gi, category: 'infrastructure', label: 'Network / Firewall Configuration' },
    ];

    const seen = new Set();
    patterns.forEach(({ regex, category, label }) => {
        if (regex.test(analysisText) && !seen.has(label)) {
            seen.add(label);
            // Extract context around the match (already clean plain text)
            regex.lastIndex = 0;
            const match = regex.exec(analysisText);
            let context = '';
            if (match) {
                const start = Math.max(0, match.index - 60);
                const end = Math.min(analysisText.length, match.index + match[0].length + 100);
                context = analysisText.slice(start, end).replace(/\n/g, ' ').trim();
                if (start > 0) context = '...' + context;
                if (end < analysisText.length) context = context + '...';
            }
            items.push({
                id: id++,
                name: label,
                description: context || `Identified from BRD analysis — ${label} may be required for this project.`,
                category,
                priority: category === 'credentials' ? 'high' : 'medium',
                fieldType: inferFieldTypeFromRequirement(label, context),
                provided: false,
                containsSecret: false,
                userValue: '',
                userFileName: '',
            });
        }
    });

    return items;
};

const normalizePrerequisiteItem = (item = {}, idx = 0) => {
    const name = String(item.name || item.title || `Prerequisite ${idx + 1}`).trim();
    const description = String(item.description || item.details || '').trim();
    const inferredFieldType = inferFieldTypeFromRequirement(name, description);
    const rawType = String(item.fieldType || '').trim().toLowerCase();
    const fieldType = rawType === 'text' || rawType === 'url' || rawType === 'file'
        ? rawType
        : inferredFieldType;

    const userValue = String(item.userValue || '').trim();
    const userFileName = String(item.userFileName || item.userFile || '').trim();
    const hasAnswer = Boolean(userValue || userFileName);

    return {
        id: item.id ?? (idx + 1),
        name: name || `Prerequisite ${idx + 1}`,
        description,
        category: String(item.category || 'other').trim() || 'other',
        priority: String(item.priority || 'medium').trim() || 'medium',
        fieldType,
        provided: typeof item.provided === 'boolean' ? item.provided : hasAnswer,
        containsSecret: Boolean(item.containsSecret),
        userValue,
        userFileName,
    };
};

const sanitizePrerequisiteForAiPayload = (item = {}) => {
    const safe = {
        name: String(item.name || '').trim() || 'Unknown',
        description: String(item.description || '').trim(),
        category: String(item.category || 'other').trim() || 'other',
        priority: String(item.priority || 'medium').trim() || 'medium',
        fieldType: String(item.fieldType || 'text').trim() || 'text',
        provided: Boolean(item.provided),
    };

    // Never pass secret-marked user-entered content to AI generation payloads.
    const isSecret = Boolean(item.containsSecret);
    safe.containsSecret = isSecret;

    const value = String(item.userValue || '').trim();
    const fileName = String(item.userFileName || '').trim();
    if (!isSecret) {
        if (value) safe.userValue = value;
        if (fileName) safe.userFileName = fileName;
    }

    return safe;
};

const parseRepoMetaSuggestion = (value = '') => {
    const raw = String(value || '').trim();
    if (!raw) return null;

    const asGithubPath = (candidate) => {
        const cleaned = String(candidate || '')
            .trim()
            .replace(/^\/+|\/+$/g, '')
            .replace(/\.git$/i, '');
        const parts = cleaned.split('/').filter(Boolean);
        if (parts.length < 2) return null;
        const path = `${parts[0]}/${parts[1]}`;
        return {
            repo: path,
            provider: 'github',
            url: `https://github.com/${path}.git`,
        };
    };

    if (/github\.com/i.test(raw)) {
        try {
            const normalizedUrl = raw.startsWith('http://') || raw.startsWith('https://')
                ? raw
                : `https://${raw}`;
            const url = new URL(normalizedUrl);
            return asGithubPath(url.pathname);
        } catch {
            // Fallback to direct path parsing below.
        }
    }

    if (/dev\.azure\.com|\.visualstudio\.com/i.test(raw)) {
        try {
            const normalizedUrl = raw.startsWith('http://') || raw.startsWith('https://')
                ? raw
                : `https://${raw}`;
            const url = new URL(normalizedUrl);
            const host = url.hostname.toLowerCase();
            const parts = url.pathname.split('/').filter(Boolean).map((p) => decodeURIComponent(p));

            let org = '';
            let project = '';
            let repo = '';

            if (host.endsWith('dev.azure.com')) {
                if (parts.length >= 4 && parts[2].toLowerCase() === '_git') {
                    [org, project] = parts;
                    repo = parts[3];
                }
            } else if (host.endsWith('.visualstudio.com')) {
                org = host.split('.visualstudio.com')[0];
                if (parts.length >= 3 && parts[1].toLowerCase() === '_git') {
                    project = parts[0];
                    repo = parts[2];
                }
            }

            repo = String(repo || '').replace(/\.git$/i, '').trim();
            if (org && project && repo) {
                return {
                    repo: `${org}/${project}/${repo}`,
                    provider: 'azure-devops',
                    url: `https://dev.azure.com/${org}/${project}/_git/${repo}`,
                };
            }
        } catch {
            // fall through
        }
    }

    return asGithubPath(raw);
};

const extractRepoSuggestionFromAnalysis = (analysisObj) => {
    if (!analysisObj || typeof analysisObj !== 'object') return null;

    const possibleSources = [
        analysisObj.repoContextMeta,
        analysisObj.repoContext,
        analysisObj.projectMeta?.repoContext,
        analysisObj.projectMeta?.repo_context,
    ].filter(Boolean);

    for (const source of possibleSources) {
        const parsed = parseRepoMetaSuggestion(
            source?.repo || source?.full_name || source?.url || source?.git_repo_url || source?.repository
        );
        if (!parsed) continue;

        return {
            repo: parsed.repo,
            branch: String(source?.branch || source?.default_branch || '').trim() || null,
            url: parsed.url,
            source: String(source?.source || 'analysis'),
            provider: parsed.provider,
        };
    }

    const analysisText = String(analysisObj.analysis || analysisObj.report || '');
    const match = analysisText.match(/Repository:\s*([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)/i);
    if (match?.[1]) {
        const parsed = parseRepoMetaSuggestion(match[1]);
        if (parsed) {
            return {
                repo: parsed.repo,
                branch: null,
                url: parsed.url,
                source: 'analysis',
                provider: parsed.provider,
            };
        }
    }

    return null;
};

const extractRepoSuggestionFromStoredMeta = (storedMeta) => {
    if (!storedMeta || typeof storedMeta !== 'object') return null;
    const parsed = parseRepoMetaSuggestion(
        storedMeta.repo || storedMeta.full_name || storedMeta.url || storedMeta.git_repo_url || storedMeta.repository
    );
    if (!parsed) return null;
    return {
        repo: parsed.repo,
        branch: String(storedMeta.branch || storedMeta.default_branch || '').trim() || null,
        url: String(storedMeta.url || parsed.url || '').trim() || parsed.url,
        source: String(storedMeta.source || 'session'),
        provider: String(storedMeta.provider || parsed.provider || 'github'),
    };
};

/* ─────────────────────────────────────────────────────────
   PRIORITY BADGE
───────────────────────────────────────────────────────── */
const PriorityBadge = ({ priority }) => {
    const config = {
        high: { bg: 'bg-app-status-errorBg', text: 'text-app-status-error', border: 'border-red-200', label: 'High' },
        medium: { bg: 'bg-app-status-warningBg', text: 'text-app-status-warning', border: 'border-amber-200', label: 'Medium' },
        low: { bg: 'bg-app-status-successBg', text: 'text-app-status-success', border: 'border-green-200', label: 'Low' },
    };
    const c = config[priority] || config.medium;
    return (
        <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${c.bg} ${c.text} ${c.border}`}>
            {c.label}
        </span>
    );
};

/* ─────────────────────────────────────────────────────────
   MAIN COMPONENT
───────────────────────────────────────────────────────── */
const PrerequisiteClassification = ({ fetchRoadmapData, selectedProjectKey, projects }) => {
    const navigate = useNavigate();
    const [prerequisites, setPrerequisites] = useState([]);
    const [loading, setLoading] = useState(true);
    const lastLoadedProjectKeyRef = useRef(null);
    const [showRedirectionConfirmation, setShowRedirectionConfirmation] = useState(false);
    const [redirectionTarget, setRedirectionTarget] = useState(null);

    // Redirect to new project page if no projects exist
    useEffect(() => {
        if (!projects || projects.length === 0) {
            const timer = setTimeout(() => {
                if (!projects || projects.length === 0) {
                    navigate('/new-project');
                }
            }, 500);
            return () => clearTimeout(timer);
        }
    }, [projects, navigate]);

    const handleConfirmRedirection = async () => {
        if (!redirectionTarget) return;
        try {
            const token = localStorage.getItem('token');
            const res = await fetch(`${API_ENDPOINTS.VIBECODING_HANDOFF}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({ project_token: selectedProjectKey }),
            });
            if (res.ok) {
                const { handoff_token } = await res.json();
                const sep = redirectionTarget.includes('?') ? '&' : '?';
                window.location.href = `${redirectionTarget}${sep}handoff_token=${encodeURIComponent(handoff_token)}`;
                return;
            }
        } catch (err) {
            console.error('Failed to get handoff token:', err);
        }
        window.location.href = redirectionTarget;
    };

    const handleCancelRedirection = () => {
        setShowRedirectionConfirmation(false);
        setSubmitting(false);
    };
    const [error, setError] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [submitted, setSubmitted] = useState(false);
    const [processMode, setProcessMode] = useState('ai_first');
    const [projectName, setProjectName] = useState('');
    const [globalGitRepoUrl, setGlobalGitRepoUrl] = useState('');
    const [globalGitToken, setGlobalGitToken] = useState('');
    const [hasSavedGlobalGitToken, setHasSavedGlobalGitToken] = useState(false);
    const [isLoadingGitConfig, setIsLoadingGitConfig] = useState(true);
    const [analysisRepoSuggestion, setAnalysisRepoSuggestion] = useState(null);
    const [repoProvider, setRepoProvider] = useState('github');
    
    // Git validation state
    const [isValidatingGit, setIsValidatingGit] = useState(false);
    const [gitValidationResult, setGitValidationResult] = useState(null);
    const [gitValidationError, setGitValidationError] = useState('');
    const [gitToastVisible, setGitToastVisible] = useState(false);
    const gitToastTimerRef = useRef(null);

    // Greenfield non-empty repo detection and strategy modal state
    const [projectType, setProjectType] = useState(() => {
        if (selectedProjectKey) {
            return localStorage.getItem(`project_type_${selectedProjectKey}`) || 'greenfield';
        }
        return 'greenfield';
    });
    const [showGreenfieldModal, setShowGreenfieldModal] = useState(false);
    const [greenfieldRepoDetails, setGreenfieldRepoDetails] = useState(null);
    const [isInspectingRepo, setIsInspectingRepo] = useState(false);
    const [greenfieldAction, setGreenfieldAction] = useState(() => {
        if (selectedProjectKey) {
            return localStorage.getItem(`greenfield_repo_action_${selectedProjectKey}`) || '';
        }
        return '';
    });
    const [greenfieldCustomInstructions, setGreenfieldCustomInstructions] = useState(() => {
        if (selectedProjectKey) {
            return localStorage.getItem(`greenfield_custom_instructions_${selectedProjectKey}`) || '';
        }
        return '';
    });
    // Temporary modal state while making a choice
    const [modalActionChoice, setModalActionChoice] = useState('wipe');
    const [modalCustomInstructions, setModalCustomInstructions] = useState('');
    const [modalNewRepoUrl, setModalNewRepoUrl] = useState('');
    const [modalNewRepoToken, setModalNewRepoToken] = useState('');
    const [modalNewRepoProvider, setModalNewRepoProvider] = useState('github');
    const [isValidatingModalNewRepo, setIsValidatingModalNewRepo] = useState(false);
    const [modalNewRepoValidation, setModalNewRepoValidation] = useState(null);
    const [modalNewRepoError, setModalNewRepoError] = useState('');

    // Auto-dismiss general error toast after 6 seconds
    useEffect(() => {
        if (error) {
            const timer = setTimeout(() => {
                setError('');
            }, 6000);
            return () => clearTimeout(timer);
        }
    }, [error]);
    
    // Claude.md file upload state
    const [claudeMdFiles, setClaudeMdFiles] = useState([]);
    const [showClaudeMdViewer, setShowClaudeMdViewer] = useState(false);
    const [selectedClaudeMdContent, setSelectedClaudeMdContent] = useState('');
    const [selectedClaudeMdName, setSelectedClaudeMdName] = useState('');
    
    // Skills.md file upload state
    const [skillsMdFiles, setSkillsMdFiles] = useState([]);
    const [showSkillsMdViewer, setShowSkillsMdViewer] = useState(false);
    const [selectedSkillsMdContent, setSelectedSkillsMdContent] = useState('');
    const [selectedSkillsMdName, setSelectedSkillsMdName] = useState('');
    
    const selectedProject = useMemo(
        () => projects?.find((project) => project.key === selectedProjectKey) || null,
        [projects, selectedProjectKey]
    );

    // Determine recommended mode based on governance classification
    const recommendedMode = useMemo(() => {
        const classification = (selectedProject?.classification || '').toUpperCase();
        if (classification === 'SANDBOX') {
            return 'ai_first';
        }
        return 'coexistence';
    }, [selectedProject]);

    const prefetchTaskToken = useCallback(async () => {
        if (!selectedProjectKey) return null;

        const cachedToken = getCachedTaskToken(selectedProjectKey);
        if (cachedToken) {
            return cachedToken;
        }

        // Prefer project-specific credentials if present; otherwise fall back to org/default creds.
        // IMPORTANT: we should not cache a token obtained via org/default creds under the project key,
        // because later the project may receive its own client_id/client_secret (from bootstrap),
        // and TaskCreation would keep using the cached org token -> "random" project/task data.
        const projectClientId = selectedProject?.client_id;
        const projectClientSecret = selectedProject?.client_secret;
        const usingProjectCredentials = Boolean(projectClientId && projectClientSecret);

        const clientId =
            projectClientId ||
            import.meta.env.VITE_TASK_API_CLIENT_ID ||
            "org_1_596a6282";
        const clientSecret =
            projectClientSecret ||
            import.meta.env.VITE_TASK_API_CLIENT_SECRET ||
            "voxtdGRCbutV0qHfRQD_Ky1yd9HeCpMuOFKxeUnYB0E";

        if (!clientId || !clientSecret) return null;

        const res = await fetch(API_ENDPOINTS.TASK_TOKEN, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                client_id: clientId,
                client_secret: clientSecret,
            }),
        });
        if (!res.ok) {
            return null;
        }

        const data = await res.json().catch(() => ({}));
        if (data?.access) {
            // Cache only if token was obtained with project-specific credentials.
            if (usingProjectCredentials) {
                cacheTaskToken(selectedProjectKey, data.access);
            }
            return data.access;
        }
        return null;
    }, [selectedProject, selectedProjectKey]);

    const loadStoredProjectRepoSuggestion = useCallback(() => {
        const currentProject = projects?.find((p) => p.key === selectedProjectKey);
        const projectToken = currentProject?.projectToken || selectedProjectKey;
        const repoKeys = [
            selectedProjectKey,
            currentProject?.projectToken,
            currentProject?.governanceResultId != null ? String(currentProject.governanceResultId) : null,
            projectToken,
        ]
            .map((value) => String(value || '').trim())
            .filter(Boolean);

        for (const key of repoKeys) {
            try {
                const storageKey = `repo_context_meta_${key}`;
                const raw =
                    sessionStorage.getItem(storageKey) ||
                    localStorage.getItem(storageKey);
                if (!raw) continue;
                const parsed = extractRepoSuggestionFromStoredMeta(JSON.parse(raw));
                if (parsed) {
                    return parsed;
                }
            } catch {
                // ignore malformed storage values and continue trying keys
            }
        }
        return null;
    }, [projects, selectedProjectKey]);

    const [customRules, setCustomRules] = useState(() => {
        if (selectedProjectKey) {
            return localStorage.getItem(`custom_rules_${selectedProjectKey}`) || '';
        }
        return '';
    });

    // Sync processMode when project changes
    useEffect(() => {
        if (!selectedProjectKey) return;
        const map = readProcessModeMap();
        if (map[selectedProjectKey]) {
            setProcessMode(map[selectedProjectKey]);
        } else {
            // Default to recommended mode based on classification
            const classification = (selectedProject?.classification || '').toUpperCase();
            if (classification === 'SANDBOX') {
                setProcessMode('ai_first');
            } else {
                setProcessMode('coexistence');
            }
        }
    }, [selectedProjectKey, selectedProject]);

    useEffect(() => {
        if (!selectedProjectKey) return;
        let cancelled = false;
        
        // Load custom rules from localStorage (user-specific, no backend endpoint)
        const saved = localStorage.getItem(`custom_rules_${selectedProjectKey}`) || '';
        setCustomRules(saved);
        
        // Load claude.md files — prefer backend (org-scoped source of truth), fallback to localStorage
        const loadClaudeMdFromBackend = async () => {
            try {
                const token = localStorage.getItem('token');
                if (!token) throw new Error('No auth token');
                const response = await fetch(API_ENDPOINTS.GOVERNANCE_CLAUDE_MD_FILES(selectedProjectKey), {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (cancelled) return;
                if (response.ok) {
                    const data = await response.json();
                    if (cancelled) return;
                    if (Array.isArray(data) && data.length > 0) {
                        setClaudeMdFiles(data);
                        // Sync backend data to localStorage for offline resilience
                        localStorage.setItem(`claude_md_files_${selectedProjectKey}`, JSON.stringify(data));
                        return; // Successfully loaded from backend
                    }
                }
            } catch (e) {
                console.warn('Failed to load claude.md files from backend:', e);
            }
            if (cancelled) return;
            // Fallback: load from localStorage
            const savedClaudeFiles = localStorage.getItem(`claude_md_files_${selectedProjectKey}`);
            if (savedClaudeFiles) {
                try {
                    setClaudeMdFiles(JSON.parse(savedClaudeFiles));
                } catch (e) {
                    console.error('Failed to parse saved claude.md files:', e);
                }
            }
        };
        
        // Load skills.md files — prefer backend (org-scoped source of truth), fallback to localStorage
        const loadSkillsMdFromBackend = async () => {
            try {
                const token = localStorage.getItem('token');
                if (!token) throw new Error('No auth token');
                const response = await fetch(API_ENDPOINTS.GOVERNANCE_SKILLS_MD_FILES(selectedProjectKey), {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (cancelled) return;
                if (response.ok) {
                    const data = await response.json();
                    if (cancelled) return;
                    if (Array.isArray(data) && data.length > 0) {
                        setSkillsMdFiles(data);
                        // Sync backend data to localStorage for offline resilience
                        localStorage.setItem(`skills_md_files_${selectedProjectKey}`, JSON.stringify(data));
                        return; // Successfully loaded from backend
                    }
                }
            } catch (e) {
                console.warn('Failed to load skills.md files from backend:', e);
            }
            if (cancelled) return;
            // Fallback: load from localStorage
            const savedSkillsFiles = localStorage.getItem(`skills_md_files_${selectedProjectKey}`);
            if (savedSkillsFiles) {
                try {
                    setSkillsMdFiles(JSON.parse(savedSkillsFiles));
                } catch (e) {
                    console.error('Failed to parse saved skills.md files:', e);
                }
            }
        };
        
        loadClaudeMdFromBackend();
        loadSkillsMdFromBackend();
        
        return () => { cancelled = true; };
    }, [selectedProjectKey]);

    useEffect(() => {
        if (selectedProjectKey) {
            localStorage.setItem(`custom_rules_${selectedProjectKey}`, customRules);
        }
    }, [selectedProjectKey, customRules]);
    
    // Save claude.md files when they change
    useEffect(() => {
        if (selectedProjectKey && claudeMdFiles.length > 0) {
            localStorage.setItem(`claude_md_files_${selectedProjectKey}`, JSON.stringify(claudeMdFiles));
            
            // Also save to backend
            const token = localStorage.getItem('token');
            if (token) {
                fetch(API_ENDPOINTS.GOVERNANCE_CLAUDE_MD_FILES(selectedProjectKey), {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(claudeMdFiles)
                }).catch(err => console.error('Failed to save claude.md files to backend:', err));
            }
        }
    }, [selectedProjectKey, claudeMdFiles]);
    
    // Save skills.md files when they change
    useEffect(() => {
        if (selectedProjectKey && skillsMdFiles.length > 0) {
            localStorage.setItem(`skills_md_files_${selectedProjectKey}`, JSON.stringify(skillsMdFiles));
            
            // Also save to backend
            const token = localStorage.getItem('token');
            if (token) {
                fetch(API_ENDPOINTS.GOVERNANCE_SKILLS_MD_FILES(selectedProjectKey), {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(skillsMdFiles)
                }).catch(err => console.error('Failed to save skills.md files to backend:', err));
            }
        }
    }, [selectedProjectKey, skillsMdFiles]);

    // Derive project name from the projects list or governance context
    useEffect(() => {
        // Try from projects list first (most reliable, project-specific)
        if (projects && selectedProjectKey) {
            const proj = projects.find(p => p.key === selectedProjectKey);
            if (proj?.name) {
                setProjectName(proj.name);
                return;
            }
        }
        // Fallback: governance context
        const savedContext = sessionStorage.getItem('governanceContext') || localStorage.getItem('governanceContext');
        if (savedContext) {
            try {
                const ctx = JSON.parse(savedContext);
                if (ctx.project_name) setProjectName(ctx.project_name);
            } catch { /* ignore */ }
        }
    }, [projects, selectedProjectKey]);

    useEffect(() => {
        let isMounted = true;
        const loadGlobalGitConfig = async () => {
            setIsLoadingGitConfig(true);
            if (!selectedProjectKey) {
                setGlobalGitRepoUrl('');
                setGlobalGitToken('');
                setHasSavedGlobalGitToken(false);
                setIsLoadingGitConfig(false);
                return;
            }
            try {
                const token = localStorage.getItem('token');
                if (!token) {
                    if (isMounted) setIsLoadingGitConfig(false);
                    return;
                }

                // 1. Try project-wise git-config endpoint first (Destination Repository)
                const configRes = await fetch(`${API_BASE_URL}/api/projects/${selectedProjectKey}/git-config`, {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (configRes.ok) {
                    const configData = await configRes.json().catch(() => ({}));
                    if (!isMounted) return;
                    setGlobalGitRepoUrl(configData.dest_repo_url || '');
                    setHasSavedGlobalGitToken(Boolean(configData.dest_repo_token));
                    setGlobalGitToken('');
                    if (configData.repo_action) {
                        setGreenfieldAction(configData.repo_action);
                        setModalActionChoice(configData.repo_action);
                    }
                    if (configData.repo_custom_instructions) {
                        setGreenfieldCustomInstructions(configData.repo_custom_instructions);
                        setModalCustomInstructions(configData.repo_custom_instructions);
                    }
                    if (configData.project_type) {
                        setProjectType(configData.project_type);
                    }
                    return;
                }

                // 2. Legacy fallback
                const url = new URL(API_ENDPOINTS.AGENTS);
                url.searchParams.set('project_token', selectedProjectKey);
                const res = await fetch(url.toString(), {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (!res.ok) return;

                const data = await res.json().catch(() => ({}));
                const agents = Array.isArray(data?.agents) ? data.agents : [];
                const repo = agents.find((a) => a?.git_repo_url)?.git_repo_url || '';
                const hasToken = agents.some((a) => a?.has_git_token);
                if (!isMounted) return;

                // Do not wipe an already-prefilled repo with an empty backend value.
                if (repo.trim()) {
                    setGlobalGitRepoUrl(repo);
                }
                setHasSavedGlobalGitToken(Boolean(hasToken));
                setGlobalGitToken('');
            } catch (e) {
                console.error('Failed to load global git config', e);
            } finally {
                if (isMounted) setIsLoadingGitConfig(false);
            }
        };

        loadGlobalGitConfig();
        return () => {
            isMounted = false;
        };
    }, [selectedProjectKey]);

    // Always prefill from the repo selected during BRD analysis for this project.
    useEffect(() => {
        if (!selectedProjectKey) return;
        const storedSuggestion = loadStoredProjectRepoSuggestion();
        if (!storedSuggestion) return;

        setAnalysisRepoSuggestion((prev) => prev || storedSuggestion);
        setGlobalGitRepoUrl((prev) => prev.trim() || storedSuggestion.url);
        if (storedSuggestion.provider === 'azure-devops') {
            setRepoProvider('azure-devops');
        } else if (storedSuggestion.provider === 'github') {
            setRepoProvider('github');
        }
    }, [selectedProjectKey, loadStoredProjectRepoSuggestion]);

    // Load analysis data for the selected project
    useEffect(() => {
        // Immediately clear previous project states when switching
        setPrerequisites([]);
        setGlobalGitRepoUrl('');
        setRepoProvider('github');
        setAnalysisRepoSuggestion(null);
        setError('');

        const loadAnalysis = async () => {
            setLoading(true);

            if (!selectedProjectKey) {
                setError('No project selected. Please select a project from the sidebar.');
                setLoading(false);
                return;
            }

            try {
                const token = localStorage.getItem('token');
                if (!token) {
                    navigate('/login');
                    return;
                }

                // Always fetch fresh prerequisites from the server to ensure org-scoped data
                // sessionStorage cache is avoided to prevent stale data across org members
                sessionStorage.removeItem(`prerequisites_v2_${selectedProjectKey}`);
                // Also clear old v1 cache
                sessionStorage.removeItem(`prerequisites_${selectedProjectKey}`);

                // Get the project info for matching
                const currentProject = projects?.find(p => p.key === selectedProjectKey);
                const govResultId = currentProject?.governanceResultId;
                const projToken = currentProject?.projectToken || selectedProjectKey;
                const projName = currentProject?.name || projectName;

                // Fetch history for this project token first, or fall back to history list
                const historyUrl = projToken ? `${API_ENDPOINTS.HISTORY}?project_token=${encodeURIComponent(projToken)}` : API_ENDPOINTS.HISTORY;
                const res = await fetch(historyUrl, {
                    headers: { Authorization: `Bearer ${token}` },
                });

                if (res.status === 401) {
                    navigate('/login');
                    return;
                }

                if (!res.ok) {
                    setError('Failed to fetch project history.');
                    setLoading(false);
                    return;
                }

                const docs = await res.json();

                // Find the document linked to THIS project specifically
                let projectDoc = docs.find(doc => {
                    const topToken = doc.project_token;
                    if (topToken && String(topToken) === String(projToken)) return true;
                    if (!doc.analysis_result) return false;
                    try {
                        const analysis = JSON.parse(doc.analysis_result);
                        const meta = analysis.projectMeta || {};
                        const govCtx = analysis.governanceContext || {};

                        const docToken = meta.project_token || govCtx.project_token || topToken;
                        const docGovId = meta.governance_result_id || govCtx.result_id;
                        const docName = meta.project_name || govCtx.project_name || '';

                        // Match by project token
                        if (docToken && String(docToken) === String(projToken)) return true;
                        // Match by governance result ID
                        if (docGovId && govResultId && String(docGovId) === String(govResultId)) return true;
                        // Match by project name (case insensitive)
                        if (projName && docName && docName.trim().toLowerCase() === projName.trim().toLowerCase()) return true;

                        return false;
                    } catch {
                        return false;
                    }
                });

                // Fallback to currentProject.latestDocument if list query didn't find a matching document
                if (!projectDoc && currentProject?.latestDocument?.analysis_result) {
                    projectDoc = currentProject.latestDocument;
                }

                if (!projectDoc?.analysis_result) {
                    setError(`No analysis found for "${projName || selectedProjectKey}". Please complete Agent Analysis first.`);
                    setPrerequisites([]);
                    setLoading(false);
                    return;
                }

                // Parse the analysis and extract prerequisites
                let analysisObj = null;
                try {
                    analysisObj = JSON.parse(projectDoc.analysis_result);
                } catch {
                    analysisObj = null;
                }

                // Extract and store project classification (greenfield / brownfield / migration)
                const docProjectType = 
                    analysisObj?.project_type ||
                    analysisObj?.metrics?.project_type ||
                    analysisObj?.stage1?.development_classification?.type ||
                    analysisObj?.projectMeta?.project_type ||
                    projectDoc?.project_type;
                if (docProjectType) {
                    const normType = String(docProjectType).trim().toLowerCase();
                    setProjectType(normType);
                    if (selectedProjectKey) {
                        localStorage.setItem(`project_type_${selectedProjectKey}`, normType);
                    }
                }

                const detectedRepo = extractRepoSuggestionFromAnalysis(analysisObj);
                const storedRepo = loadStoredProjectRepoSuggestion();

                // CRITICAL FIX: For NEW projects, only use repo suggestion if it came from explicit user input
                // Don't auto-populate from BRD text analysis (which might just be mentioning an example repo)
                const finalRepoSuggestion = storedRepo || (detectedRepo?.source === 'link' ? detectedRepo : null);
                
                // Only set repo suggestion if we have a valid one from user input
                if (finalRepoSuggestion) {
                    setAnalysisRepoSuggestion(finalRepoSuggestion);
                    if (finalRepoSuggestion?.url) {
                        setGlobalGitRepoUrl((prev) => prev.trim() || finalRepoSuggestion.url);
                    }
                    if (finalRepoSuggestion?.provider === 'azure-devops') {
                        setRepoProvider('azure-devops');
                    } else if (finalRepoSuggestion?.provider === 'github') {
                        setRepoProvider('github');
                    }
                }

                // Use structured prerequisites from AI if available, otherwise fall back to text extraction
                const extracted = extractPrerequisitesFromAnalysis(analysisObj || projectDoc.analysis_result);
                let initialPrereqs = extracted.map((p, idx) => normalizePrerequisiteItem(p, idx));

                // Check if user has saved prerequisite inputs in backend DB first
                try {
                    const dbPrereqRes = await fetch(`${API_BASE_URL}/governance/prerequisites/${selectedProjectKey}`, {
                        headers: { Authorization: `Bearer ${token}` }
                    });
                    if (dbPrereqRes.ok) {
                        const dbData = await dbPrereqRes.json();
                        const savedDbItems = Array.isArray(dbData?.prerequisites) ? dbData.prerequisites : [];
                        if (savedDbItems.length > 0) {
                            // Merge DB saved values into initialPrereqs
                            initialPrereqs = initialPrereqs.map((p) => {
                                const matchedSaved = savedDbItems.find(
                                    (s) => s.id === p.id || (s.name && p.name && s.name.trim().toLowerCase() === p.name.trim().toLowerCase())
                                );
                                if (matchedSaved) {
                                    return {
                                        ...p,
                                        provided: matchedSaved.provided ?? p.provided,
                                        userValue: matchedSaved.userValue ?? p.userValue,
                                        userFileName: matchedSaved.userFileName ?? p.userFileName,
                                        containsSecret: matchedSaved.containsSecret ?? p.containsSecret,
                                    };
                                }
                                return p;
                            });
                        }
                    }
                } catch (dbErr) {
                    console.warn('Failed to load DB prerequisites:', dbErr);
                }

                setPrerequisites(initialPrereqs);
                } catch (err) {
                    console.error('Failed to load analysis data:', err);
                    setError(sanitizeErrorMessage(err));
                } finally {
                setLoading(false);
            }
        };

        loadAnalysis();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedProjectKey, navigate, projects, loadStoredProjectRepoSuggestion]);

    // Save prerequisites to session and backend DB when they change
    useEffect(() => {
        if (prerequisites.length > 0 && selectedProjectKey) {
            sessionStorage.setItem(
                `prerequisites_v2_${selectedProjectKey}`,
                JSON.stringify(prerequisites)
            );

            // Auto-save user selections and inputs to backend DB
            const timer = setTimeout(() => {
                const token = localStorage.getItem('token');
                if (token) {
                    const sanitizedPayload = prerequisites.map(p => sanitizePrerequisiteForAiPayload(p));
                    fetch(`${API_BASE_URL}/governance/prerequisites/${selectedProjectKey}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            Authorization: `Bearer ${token}`,
                        },
                        body: JSON.stringify({ prerequisites: sanitizedPayload }),
                    }).catch(err => console.warn('Failed to auto-save prerequisites to DB:', err));
                }
            }, 800);

            return () => clearTimeout(timer);
        }
    }, [prerequisites, selectedProjectKey]);

    const toggleProvided = useCallback((id) => {
        setPrerequisites(prev =>
            prev.map(p => p.id === id ? { ...p, provided: !p.provided } : p)
        );
    }, []);

    // Toggle secret flag - secret-marked answers are excluded from AI payloads.
    const toggleSecret = useCallback((id) => {
        setPrerequisites(prev =>
            prev.map(p => p.id === id ? { ...p, containsSecret: !p.containsSecret } : p)
        );
    }, []);

    // Update free‑form value for text/url fields
    const updateValue = useCallback((id, val) => {
        setPrerequisites(prev =>
            prev.map((p) => {
                if (p.id !== id) return p;
                const normalized = String(val || '');
                return {
                    ...p,
                    userValue: normalized,
                    provided: normalized.trim().length > 0,
                };
            })
        );
    }, []);

    // Store selected file (only name is kept for simplicity)
    const updateFile = useCallback((id, file) => {
        setPrerequisites(prev =>
            prev.map((p) => {
                if (p.id !== id) return p;
                const fileName = file?.name ? String(file.name) : '';
                return {
                    ...p,
                    userFileName: fileName,
                    provided: Boolean(fileName),
                };
            })
        );
    }, []);
    
    // Handle claude.md file upload
    const handleClaudeMdUpload = useCallback((event) => {
        const files = Array.from(event.target.files || []);
        const mdFiles = files.filter(file => file.name.toLowerCase().endsWith('.md'));
        
        if (mdFiles.length === 0) {
            setError('Please upload only .md files');
            return;
        }
        
        mdFiles.forEach(file => {
            const reader = new FileReader();
            reader.onload = (e) => {
                const content = e.target.result;
                setClaudeMdFiles(prev => {
                    // Check if file already exists
                    const existingIndex = prev.findIndex(f => f.name === file.name);
                    if (existingIndex >= 0) {
                        // Replace existing file
                        const updated = [...prev];
                        updated[existingIndex] = {
                            name: file.name,
                            content: content,
                            uploadedAt: new Date().toISOString(),
                        };
                        return updated;
                    } else {
                        // Add new file
                        return [...prev, {
                            name: file.name,
                            content: content,
                            uploadedAt: new Date().toISOString(),
                        }];
                    }
                });
            };
            reader.onerror = () => {
                setError(`Failed to read file: ${file.name}`);
            };
            reader.readAsText(file);
        });
        
        // Clear the input
        event.target.value = '';
    }, []);
    
    // Handle viewing claude.md file
    const handleViewClaudeMd = useCallback((file) => {
        setSelectedClaudeMdContent(file.content);
        setSelectedClaudeMdName(file.name);
        setShowClaudeMdViewer(true);
    }, []);
    
    // Handle removing claude.md file
    const handleRemoveClaudeMd = useCallback((fileName) => {
        setClaudeMdFiles(prev => prev.filter(f => f.name !== fileName));
        if (selectedProjectKey) {
            const updated = claudeMdFiles.filter(f => f.name !== fileName);
            if (updated.length === 0) {
                localStorage.removeItem(`claude_md_files_${selectedProjectKey}`);
            }
        }
    }, [selectedProjectKey, claudeMdFiles]);
    
    // Handle skills.md file upload
    const handleSkillsMdUpload = useCallback((event) => {
        const files = Array.from(event.target.files || []);
        
        files.forEach(file => {
            if (!file.name.endsWith('.md')) {
                alert(`${file.name} is not a markdown file. Only .md files are allowed.`);
                return;
            }
            
            const reader = new FileReader();
            reader.onload = (e) => {
                const content = e.target.result;
                setSkillsMdFiles(prev => {
                    // Check if file already exists
                    const existingIndex = prev.findIndex(f => f.name === file.name);
                    const newFile = {
                        name: file.name,
                        content: content,
                        uploadedAt: new Date().toISOString()
                    };
                    
                    if (existingIndex >= 0) {
                        // Replace existing file
                        const updated = [...prev];
                        updated[existingIndex] = newFile;
                        return updated;
                    } else {
                        // Add new file
                        return [...prev, newFile];
                    }
                });
            };
            reader.readAsText(file);
        });
        
        // Clear the input
        event.target.value = '';
    }, []);
    
    // Handle viewing skills.md file
    const handleViewSkillsMd = useCallback((file) => {
        setSelectedSkillsMdContent(file.content);
        setSelectedSkillsMdName(file.name);
        setShowSkillsMdViewer(true);
    }, []);
    
    // Handle removing skills.md file
    const handleRemoveSkillsMd = useCallback((fileName) => {
        setSkillsMdFiles(prev => prev.filter(f => f.name !== fileName));
        if (selectedProjectKey) {
            const updated = skillsMdFiles.filter(f => f.name !== fileName);
            if (updated.length === 0) {
                localStorage.removeItem(`skills_md_files_${selectedProjectKey}`);
            }
        }
    }, [selectedProjectKey, skillsMdFiles]);

    // Group by category
    const grouped = useMemo(() => {
        const groups = {};
        prerequisites.forEach(p => {
            if (!groups[p.category]) groups[p.category] = [];
            groups[p.category].push(p);
        });
        return groups;
    }, [prerequisites]);

    // Validate Git connection
    const showGitToast = useCallback((message) => {
        setGitValidationError(message);
        setGitToastVisible(true);
        if (gitToastTimerRef.current) clearTimeout(gitToastTimerRef.current);
        gitToastTimerRef.current = setTimeout(() => {
            setGitToastVisible(false);
            gitToastTimerRef.current = null;
        }, 5000);
    }, []);

    const hideGitToast = useCallback(() => {
        setGitToastVisible(false);
        if (gitToastTimerRef.current) {
            clearTimeout(gitToastTimerRef.current);
            gitToastTimerRef.current = null;
        }
    }, []);

    // Cleanup git toast timer on unmount
    useEffect(() => {
        return () => {
            if (gitToastTimerRef.current) {
                clearTimeout(gitToastTimerRef.current);
                gitToastTimerRef.current = null;
            }
        };
    }, []);

    const handleValidateGitConnection = useCallback(async () => {
        if (!globalGitRepoUrl.trim()) {
            showGitToast('Please enter a repository URL first');
            return;
        }

        setIsValidatingGit(true);
        setGitValidationError('');
        setGitValidationResult(null);
        setGitToastVisible(false);

        try {
            const token = localStorage.getItem('token');
            const response = await fetch(API_ENDPOINTS.GIT_VALIDATE_CONNECTION, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({
                    repo_url: globalGitRepoUrl.trim(),
                    pat: globalGitToken.trim() || null,
                    provider: repoProvider,
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Validation failed');
            }

            setGitValidationResult(data);
            
            // If URL was normalized, update the input field
            if (data.normalized_url && data.normalized_url !== globalGitRepoUrl.trim()) {
                setGlobalGitRepoUrl(data.normalized_url);
            }

            // Inspect repository contents for greenfield compatibility
            const isGreenfield = (projectType || '').toLowerCase() === 'greenfield';
            if (isGreenfield) {
                await inspectGreenfieldRepo(
                    data.normalized_url || globalGitRepoUrl.trim(),
                    globalGitToken.trim() || null,
                    repoProvider
                );
            }
        } catch (err) {
            console.error('Git validation error:', err);
            showGitToast(sanitizeErrorMessage(err));
        } finally {
            setIsValidatingGit(false);
        }
    }, [globalGitRepoUrl, globalGitToken, repoProvider, showGitToast, projectType]);

    const inspectGreenfieldRepo = useCallback(async (targetUrl, targetPat, targetProvider) => {
        if (!targetUrl || !targetUrl.trim()) return null;
        setIsInspectingRepo(true);
        try {
            const token = localStorage.getItem('token');
            const res = await fetch(API_ENDPOINTS.GIT_INSPECT_REPO, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({
                    repo_url: targetUrl.trim(),
                    pat: targetPat ? targetPat.trim() : null,
                    provider: targetProvider || repoProvider,
                    project_token: selectedProjectKey,
                }),
            });
            if (res.ok) {
                const details = await res.json();
                setGreenfieldRepoDetails(details);
                const isGreenfield = (projectType || '').toLowerCase() === 'greenfield';
                if (isGreenfield && details.has_code && !details.is_empty) {
                    setShowGreenfieldModal(true);
                    return details;
                }
            }
        } catch (e) {
            console.warn('[GitInspect] Error inspecting repository:', e);
        } finally {
            setIsInspectingRepo(false);
        }
        return null;
    }, [projectType, repoProvider, selectedProjectKey]);

    const handleApplyGreenfieldStrategy = async () => {
        let actionToSave = modalActionChoice;
        let customToSave = '';
        if (modalActionChoice === 'new_repo') {
            if (!modalNewRepoUrl.trim()) {
                setModalNewRepoError('Please enter a new repository URL.');
                return;
            }
            setGlobalGitRepoUrl(modalNewRepoUrl.trim());
            if (modalNewRepoToken) {
                setGlobalGitToken(modalNewRepoToken.trim());
            }
            setGreenfieldAction('new_repo');
            localStorage.setItem(`greenfield_repo_action_${selectedProjectKey}`, 'new_repo');
        } else if (modalActionChoice === 'wipe') {
            setGreenfieldAction('wipe');
            localStorage.setItem(`greenfield_repo_action_${selectedProjectKey}`, 'wipe');
        } else if (modalActionChoice === 'custom') {
            if (!modalCustomInstructions.trim()) {
                setModalNewRepoError('Please provide custom instructions for the agents.');
                return;
            }
            customToSave = modalCustomInstructions.trim();
            setGreenfieldAction('custom');
            setGreenfieldCustomInstructions(customToSave);
            localStorage.setItem(`greenfield_repo_action_${selectedProjectKey}`, 'custom');
            localStorage.setItem(`greenfield_custom_instructions_${selectedProjectKey}`, customToSave);
        }

        // Instantly sync greenfield strategy with backend git-config API
        try {
            const syncPayload = {
                repo_action: actionToSave,
                repo_custom_instructions: customToSave || null,
            };
            if (modalActionChoice === 'new_repo') {
                syncPayload.dest_repo_url = modalNewRepoUrl.trim();
                if (modalNewRepoToken) syncPayload.dest_repo_token = modalNewRepoToken.trim();
            }
            await fetch(`${API_BASE_URL}/api/projects/${selectedProjectKey}/git-config`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify(syncPayload),
            });
        } catch (syncErr) {
            console.warn('[handleApplyGreenfieldStrategy] Failed to sync git-config with backend:', syncErr);
        }

        setShowGreenfieldModal(false);
        setModalNewRepoError('');
    };

    const handleValidateModalNewRepo = async () => {
        if (!modalNewRepoUrl.trim()) {
            setModalNewRepoError('Please enter a repository URL to test.');
            return;
        }
        setIsValidatingModalNewRepo(true);
        setModalNewRepoError('');
        setModalNewRepoValidation(null);
        try {
            const token = localStorage.getItem('token');
            const res = await fetch(API_ENDPOINTS.GIT_VALIDATE_CONNECTION, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({
                    repo_url: modalNewRepoUrl.trim(),
                    pat: modalNewRepoToken.trim() || null,
                    provider: modalNewRepoProvider,
                }),
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || 'Validation failed for new repository');
            }
            setModalNewRepoValidation(data);
            if (data.normalized_url) {
                setModalNewRepoUrl(data.normalized_url);
            }
            // Inspect new repo
            const inspectRes = await fetch(API_ENDPOINTS.GIT_INSPECT_REPO, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({
                    repo_url: (data.normalized_url || modalNewRepoUrl).trim(),
                    pat: modalNewRepoToken.trim() || null,
                    provider: modalNewRepoProvider,
                    project_token: selectedProjectKey,
                }),
            });
            if (inspectRes.ok) {
                const inspectData = await inspectRes.json();
                if (inspectData.has_code && !inspectData.is_empty) {
                    setModalNewRepoError(`Warning: The new repository also contains ${inspectData.total_files} file(s). Recommended to use an empty repo or choose Wipe.`);
                }
            }
        } catch (err) {
            setModalNewRepoError(sanitizeErrorMessage(err));
        } finally {
            setIsValidatingModalNewRepo(false);
        }
    };

    const totalItems = prerequisites.length;
    const providedCount = prerequisites.filter(p => p.provided).length;
    const progress = totalItems > 0 ? Math.round((providedCount / totalItems) * 100) : 0;
    const allProvided = ['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode) ? true : (totalItems > 0 && providedCount === totalItems);
    const shouldShowRepoSuggestion = Boolean(
        analysisRepoSuggestion &&
        !isLoadingGitConfig &&
        !['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode)
    );
    const isGlobalGitConfigValid = ['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode) || Boolean(
        globalGitRepoUrl.trim()
    );

    const handleSubmit = async () => {
        setSubmitting(true);
        try {
            const token = localStorage.getItem('token');
            if (!token) {
                navigate('/login');
                return;
            }
            if (!selectedProjectKey) {
                throw new Error('Please select a project from the sidebar before proceeding.');
            }

            if (!['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode)) {
                const repo = globalGitRepoUrl.trim();
                const pat = globalGitToken.trim();
                if (!repo) {
                    throw new Error('Git repository URL is required.');
                }
                
                // Basic URL validation
                try {
                    new URL(repo);
                } catch {
                    throw new Error('Please enter a valid Git repository URL (e.g., https://github.com/org/repo.git).');
                }

                // Greenfield existing repo conflict protection
                const isGreenfield = (projectType || '').toLowerCase() === 'greenfield';
                if (isGreenfield && !greenfieldAction && repo) {
                    const inspection = await inspectGreenfieldRepo(repo, pat, repoProvider);
                    if (inspection && inspection.has_code && !inspection.is_empty) {
                        setSubmitting(false);
                        setShowGreenfieldModal(true);
                        return;
                    }
                }
                
                // Save global Git config from prerequisites so all agents reuse it.
                const sourceUrl = analysisRepoSuggestion?.url || repo;
                localStorage.setItem(`source_repo_url_${selectedProjectKey}`, sourceUrl);

                // 1. Save destination Git config to project-wise git-config endpoint
                const destGitConfigPayload = {
                    dest_repo_url: repo,
                };
                if (pat) destGitConfigPayload.dest_repo_token = pat;
                if (greenfieldAction) destGitConfigPayload.repo_action = greenfieldAction;
                if (greenfieldCustomInstructions) destGitConfigPayload.repo_custom_instructions = greenfieldCustomInstructions;
                if (projectType) destGitConfigPayload.project_type = projectType;

                const destConfigRes = await fetch(`${API_BASE_URL}/api/projects/${selectedProjectKey}/git-config`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify(destGitConfigPayload),
                });
                
                if (!destConfigRes.ok) {
                    const errData = await destConfigRes.json().catch(() => ({}));
                    const errorMsg = errData?.detail || 'Failed to save project Git configuration.';
                    throw new Error(sanitizeErrorMessage(errorMsg));
                }
                
                // 2. Fallback update to legacy AgentCredential table
                const agentsUrl = new URL(API_ENDPOINTS.AGENTS);
                agentsUrl.searchParams.set('project_token', selectedProjectKey);
                const agentsRes = await fetch(agentsUrl.toString(), {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (!agentsRes.ok) {
                    const agentsError = await agentsRes.json().catch(() => ({}));
                    const errorMsg = agentsError?.detail || 'Failed to load project agents.';
                    throw new Error(sanitizeErrorMessage(errorMsg));
                }
                const agentsData = await agentsRes.json().catch(() => ({}));
                const agentList = Array.isArray(agentsData?.agents) ? agentsData.agents : [];
                const targetAgent =
                    agentList.find((a) => a?.id !== 'agent_03' && a?.id !== 'agent_04') || agentList[0];
                if (!targetAgent?.id) {
                    throw new Error('No agents are available for this project. Please contact support.');
                }

                const updateUrl = new URL(API_ENDPOINTS.AGENT_UPDATE(targetAgent.id));
                updateUrl.searchParams.set('project_token', selectedProjectKey);
                const gitPayload = { git_repo_url: repo };
                if (pat) gitPayload.git_token = pat;

                const updateRes = await fetch(updateUrl.toString(), {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify(gitPayload),
                });
                
                if (!updateRes.ok) {
                    const errData = await updateRes.json().catch(() => ({}));
                    const errorMsg = errData?.detail || 'Failed to save Git configuration.';
                    throw new Error(sanitizeErrorMessage(errorMsg));
                }
                setHasSavedGlobalGitToken(true);
                setGlobalGitToken('');
            }

            // Build the prerequisite summary to persist
            const prerequisiteData = {
                completedAt: new Date().toISOString(),
                projectKey: selectedProjectKey,
                projectName: projectName,
                progress,
                totalItems,
                providedCount,
                greenfield_repo_action: greenfieldAction,
                greenfield_custom_instructions: greenfieldCustomInstructions,
                // Persist all items with their provided flag so UI can be restored fully.
                items: prerequisites.map((p) => sanitizePrerequisiteForAiPayload(p)),
            };

            // Save to localStorage (persistent) so task generation can use it
            localStorage.setItem(
                `prerequisites_completed_${selectedProjectKey}`,
                JSON.stringify(prerequisiteData)
            );

            // Save custom rules
            localStorage.setItem(`custom_rules_${selectedProjectKey}`, customRules);

            // Also update the v2 session cache
            sessionStorage.setItem(
                `prerequisites_v2_${selectedProjectKey}`,
                JSON.stringify(prerequisites)
            );

            // Mark prerequisites as completed on the backend with payload
            try {
                await fetch(API_ENDPOINTS.GOVERNANCE_PREREQUISITES_COMPLETE(selectedProjectKey), {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        prerequisites: prerequisites.map(p => sanitizePrerequisiteForAiPayload(p)),
                        custom_rules: customRules,
                        repo_action: greenfieldAction || null,
                        repo_custom_instructions: greenfieldCustomInstructions || null,
                        greenfield_repo_action: greenfieldAction || null,
                        greenfield_custom_instructions: greenfieldCustomInstructions || null,
                    }),
                });
            } catch (err) {
                console.warn('Failed to mark prerequisites as completed on backend:', err);
                // Don't throw here - this is not critical for user flow
            }

            // Refresh roadmap to reflect that prerequisites are done
            try {
                if (fetchRoadmapData && selectedProjectKey) {
                    await fetchRoadmapData(selectedProjectKey);
                }
            } catch (err) {
                console.warn('Failed to refresh roadmap data:', err);
                // Don't throw here - this is not critical for user flow
            }

            // Save selected execution mode
            saveProcessModeForProject(selectedProjectKey, processMode);

            let resolvedTaskToken = null;
            try {
                resolvedTaskToken = await prefetchTaskToken();
            } catch (prefetchError) {
                console.error('Task token prefetch failed', prefetchError);
            }

            if (['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode)) {
                // For VibeCoding mode, prepare handoff with BRD data
                if (processMode === 'vibe_coding') {
                    try {
                        // Get the BRD analysis data for this project
                        const historyRes = await fetch(API_ENDPOINTS.HISTORY, {
                            headers: { Authorization: `Bearer ${token}` },
                        });
                        
                        if (!historyRes.ok) {
                            throw new Error('Failed to fetch project analysis for VibeCoding handoff');
                        }
                        
                        const docs = await historyRes.json();
                        
                        // Find the document linked to THIS project
                        const currentProject = projects?.find(p => p.key === selectedProjectKey);
                        const govResultId = currentProject?.governanceResultId;
                        const projToken = currentProject?.projectToken || selectedProjectKey;
                        const projName = currentProject?.name || projectName;
                        
                        const projectDoc = docs.find(doc => {
                            if (!doc.analysis_result) return false;
                            try {
                                const analysis = JSON.parse(doc.analysis_result);
                                const meta = analysis.projectMeta || {};
                                const govCtx = analysis.governanceContext || {};
                                
                                const docToken = meta.project_token || govCtx.project_token;
                                const docGovId = meta.governance_result_id || govCtx.result_id;
                                const docName = meta.project_name || govCtx.project_name || '';
                                
                                if (docToken && String(docToken) === String(projToken)) return true;
                                if (docGovId && govResultId && String(docGovId) === String(govResultId)) return true;
                                if (projName && docName && docName.trim().toLowerCase() === projName.trim().toLowerCase()) return true;
                                
                                return false;
                            } catch {
                                return false;
                            }
                        });
                        
                        if (!projectDoc?.analysis_result) {
                            throw new Error('No BRD analysis found for this project. Please complete Agent Analysis first.');
                        }
                        
                        // Parse the analysis
                        let analysisObj = null;
                        try {
                            analysisObj = JSON.parse(projectDoc.analysis_result);
                        } catch {
                            analysisObj = { analysis: projectDoc.analysis_result };
                        }
                        
                        // Get the raw BRD text
                        const brdText = projectDoc.document_text || analysisObj.analysis || analysisObj.report || '';
                        
                        // Create VibeCoding handoff payload
                        const vibeHandoffPayload = {
                            project_token: selectedProjectKey,
                            project_name: projectName,
                            brd_text: brdText,
                            analysis_data: analysisObj,
                            prerequisites: prerequisites
                                .filter((p) => p.provided)
                                .map((p) => sanitizePrerequisiteForAiPayload(p)),
                            custom_rules: customRules,
                            process_mode: 'vibe_coding',
                            governance_context: (() => {
                                try {
                                    const raw = sessionStorage.getItem('governanceContext') || localStorage.getItem('governanceContext');
                                    return raw ? JSON.parse(raw) : null;
                                } catch {
                                    return null;
                                }
                            })(),
                        };
                        
                        // Get handoff token from backend
                        const handoffRes = await fetch(API_ENDPOINTS.VIBECODING_HANDOFF, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                Authorization: `Bearer ${token}`,
                            },
                            body: JSON.stringify(vibeHandoffPayload),
                        });
                        
                        if (!handoffRes.ok) {
                            const errData = await handoffRes.json().catch(() => ({}));
                            throw new Error(errData?.detail || 'Failed to create VibeCoding handoff token');
                        }
                        
                        const { handoff_token } = await handoffRes.json();
                        
                        // Construct VibeCoding URL with handoff token
                        const vibeUrl = new URL(VIBE_WORKSPACE_URL);
                        vibeUrl.searchParams.set('handoff_token', handoff_token);
                        vibeUrl.searchParams.set('source', 'dsuite');
                        vibeUrl.searchParams.set('project_token', selectedProjectKey);
                        vibeUrl.searchParams.set('auto_execute', 'true');  // Signal to auto-trigger execution
                        
                        // Save current route to return to after VibeCoding
                        const returnPath = location.pathname + location.search;
                        sessionStorage.setItem('dsuite_return_path', returnPath);
                        sessionStorage.setItem('dsuite_return_project', selectedProjectKey);
                        console.log('💾 Saved return path for D-Suite:', returnPath);
                        
                        // Open VibeCoding in new window
                        const vibeWindow = window.open(vibeUrl.toString(), '_blank');
                        
                        if (!vibeWindow) {
                            // Popup blocked - show message and provide link
                            setError('Popup blocked. Please allow popups for this site and try again, or click the link below to open VibeCoding manually.');
                            setRedirectionTarget(vibeUrl.toString());
                            setShowRedirectionConfirmation(true);
                            setSubmitting(false);
                            return;
                        }
                        
                        // Show success message
                        setSubmitted(true);
                        setTimeout(() => {
                            // Optionally redirect back to dashboard after opening VibeCoding
                            navigate('/dashboard');
                        }, 2000);
                        
                    } catch (err) {
                        console.error('VibeCoding handoff error:', err);
                        setError(sanitizeErrorMessage(err));
                        setSubmitting(false);
                        return;
                    }
                } else {
                    // For developer_only and ai_assist modes, redirect to VS Code extension
                    window.location.href = 'vscode:extension/bourntec-Solutions.n-mod-vscode-assistant';
                }
                return; // Stop execution here so it doesn't clear the submitting state right away
            } else {
                // Bootstrap/create the external task project HERE (prerequisites step),
                // using a mode-derived project deadline.
                const taskToken = resolvedTaskToken || getCachedTaskToken(selectedProjectKey);
                const bootstrapRes = await fetch(API_ENDPOINTS.AGENT_PROJECT_BOOTSTRAP, {
                    method: 'POST',
                    headers: (() => {
                        const headers = {
                            'Content-Type': 'application/json',
                            Authorization: `Bearer ${token}`,
                        };
                        if (taskToken) headers['x-task-token'] = taskToken;
                        return headers;
                    })(),
                    body: JSON.stringify({
                        project_token: selectedProjectKey,
                        project_name: projectName,
                        // Only send prerequisites that the user has actually marked as provided/checked.
                        prerequisites: prerequisites
                            .filter((p) => p.provided)
                            .map((p) => sanitizePrerequisiteForAiPayload(p)),
                        custom_rules: customRules,
                        process_mode: processMode,
                    }),
                });
                const bootstrapJson = await bootstrapRes.json().catch(() => ({}));
                if (!bootstrapRes.ok) {
                    const errorMsg = bootstrapJson?.detail || 'Failed to create project during prerequisites.';
                    console.warn('Project bootstrap warning (proceeding with local flow):', errorMsg);
                }

                // If bootstrap returned external task credentials, persist them into the draft project
                // immediately so TaskCreation can resolve a project-specific task token without relogin.
                try {
                    const appData =
                        bootstrapJson?.project?.project_application ||
                        bootstrapJson?.project_application ||
                        bootstrapJson?.project?.projectApplication ||
                        null;
                    const clientId = typeof appData?.client_id === 'string' ? appData.client_id : '';
                    const clientSecret = typeof appData?.client_secret === 'string' ? appData.client_secret : '';
                    if (clientId && clientSecret) {
                        upsertDraftProject({
                            key: selectedProjectKey,
                            projectToken: selectedProjectKey,
                            name: projectName,
                            client_id: clientId,
                            client_secret: clientSecret,
                        });
                    }
                } catch {
                    // ignore draft persistence failures
                }

                setSubmitted(true);
                // After a brief success animation, redirect to Task Creation
                setTimeout(() => {
                    navigate('/task-creation', { state: { fromPrerequisites: true } });
                }, 1500);
            }
        } catch (err) {
            console.error('Prerequisites submission error:', err);
            setError(sanitizeErrorMessage(err));
        } finally {
            if (!['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode)) {
                setSubmitting(false);
            }
        }
    };

    /* ── Loading State ── */
    if (loading || isLoadingGitConfig) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">
                <div className="flex flex-col items-center gap-5">
                    <div className="relative">
                        <div className="w-14 h-14 border-4 border-app-primary-ring border-t-blue-600 rounded-full animate-spin" />
                        <div className="absolute inset-0 w-14 h-14 border-4 border-transparent border-b-indigo-400 rounded-full animate-spin" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }} />
                    </div>
                    <div className="text-center">
                        <p className="text-app-text-label font-semibold text-sm tracking-wide">
                            {isLoadingGitConfig ? "Retrieving git configuration…" : "Analyzing prerequisites…"}
                        </p>
                        <p className="text-app-text-light text-xs mt-1">
                            {isLoadingGitConfig ? "Checking project repository settings" : "Extracting requirements from AI analysis"}
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    /* ── Submitted Success State ── */
    if (submitted) {
        return (
            <div className="h-full overflow-y-auto bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">
                <div className="max-w-2xl mx-auto px-4 py-16">
                    <div className="bg-app-bg-card/90 backdrop-blur-xl rounded-2xl shadow-lg border border-app-bg-card/60 p-10 text-center relative overflow-hidden">
                        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-app-status-success via-teal-500 to-app-status-success rounded-t-2xl" />

                        <div className="w-20 h-20 mx-auto mb-6 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-full flex items-center justify-center shadow-lg shadow-emerald-200">
                            <CheckCircle2 className="w-10 h-10 text-white" />
                        </div>

                        <h2 className="text-2xl font-extrabold text-app-text-main mb-2 tracking-tight">
                            {processMode === 'vibe_coding' ? 'VibeCoding Launched' : 'Prerequisites Acknowledged'}
                        </h2>
                        <p className="text-app-text-muted text-sm mb-6 leading-relaxed max-w-md mx-auto">
                            {processMode === 'vibe_coding' ? (
                                <>
                                    VibeCoding workspace opened with BRD for{" "}
                                    <strong>{projectName || 'this project'}</strong>.
                                    {" "}Project creation and task execution will begin automatically.
                                </>
                            ) : (
                                <>
                                    {providedCount} of {totalItems} prerequisite items have been confirmed for{" "}
                                    <strong>{projectName || 'this project'}</strong>.
                                </>
                            )}
                        </p>

                        <div className="flex items-center justify-center gap-2 text-sm text-app-text-light">
                            <div className="w-4 h-4 border-2 border-app-border border-t-emerald-500 rounded-full animate-spin" />
                            {['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode) 
                                ? 'VibeCoding workspace is ready…' 
                                : 'Redirecting to Task Creation…'
                            }
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    /* ── Main View ── */
    return (
        <div className="h-full overflow-y-auto bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">
            {/* Redirection Confirmation Modal */}
            {showRedirectionConfirmation && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                    <div className="bg-app-bg-card rounded-2xl shadow-2xl border border-app-border max-w-md w-full p-6">
                        <div className="flex items-start gap-4 mb-4">
                            <div className="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center flex-shrink-0">
                                <AlertTriangle className="w-6 h-6 text-amber-600" />
                            </div>
                            <div className="flex-1">
                                <h3 className="text-lg font-bold text-app-text-main mb-1">Popup Blocked</h3>
                                <p className="text-sm text-app-text-muted leading-relaxed">
                                    Your browser blocked the VibeCoding window. Please allow popups for this site and try again, or click the button below to open VibeCoding manually.
                                </p>
                            </div>
                        </div>
                        <div className="flex gap-3">
                            <button
                                onClick={handleCancelRedirection}
                                className="flex-1 px-4 py-2.5 text-sm font-semibold text-app-text-main bg-app-bg-page border border-app-border rounded-lg hover:bg-app-bg-hover transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleConfirmRedirection}
                                className="flex-1 px-4 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-app-primary to-app-primary-hover rounded-lg hover:shadow-lg transition-all"
                            >
                                Open VibeCoding
                            </button>
                        </div>
                    </div>
                </div>
            )}
            
            <div className="px-3 sm:px-4 lg:px-6 py-4 lg:py-6 max-w-[1200px] mx-auto">

                {/* Back Link */}
                <button
                    onClick={() => navigate('/dashboard')}
                    className="inline-flex items-center gap-1.5 text-sm font-semibold text-app-text-muted hover:text-app-text-main mb-5 transition-colors group"
                >
                    <ChevronLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" /> Back to Requirement Screening
                </button>

                {/* ── HERO HEADER ── */}
                <div className="relative rounded-2xl overflow-hidden bg-gradient-to-br from-app-hero-bg via-app-hero-bg to-app-sidebar-bg text-white p-6 sm:p-8 shadow-xl mb-6">
                    <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center gap-5">
                        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-4 flex-shrink-0">
                            <KeyRound className="w-12 h-12 text-amber-400" />
                        </div>
                        <div className="flex-1 min-w-0">
                            <p className="text-white/60 text-xs font-semibold uppercase tracking-widest mb-1 flex items-center gap-1.5">
                                <Sparkles className="w-3 h-3" /> AI-Generated Prerequisites
                            </p>
                            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight mb-1">
                                Prerequisite Classification
                            </h1>
                            <p className="text-white/70 text-sm">
                                {projectName ? `For "${projectName}" — ` : ''}
                                Review and confirm the prerequisites identified from your BRD analysis.
                            </p>
                        </div>

                        {/* Progress Ring */}
                        <div className="flex-shrink-0 hidden sm:block">
                            <div className="relative w-24 h-24">
                                <svg className="w-24 h-24 -rotate-90" viewBox="0 0 96 96">
                                    <circle cx="48" cy="48" r="38" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="8" />
                                    <circle cx="48" cy="48" r="38" fill="none" stroke="#fbbf24" strokeWidth="8"
                                        strokeLinecap="round"
                                        strokeDasharray={`${2 * Math.PI * 38}`}
                                        strokeDashoffset={`${2 * Math.PI * 38 * (1 - progress / 100)}`}
                                        style={{ transition: 'stroke-dashoffset 0.6s ease-out' }}
                                    />
                                </svg>
                                <div className="absolute inset-0 flex flex-col items-center justify-center">
                                    <span className="text-xl font-extrabold text-white">{progress}%</span>
                                    <span className="text-[9px] font-semibold text-white/50 uppercase">Done</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Decorative circles */}
                    <div className="absolute -top-10 -right-10 w-40 h-40 bg-white/5 rounded-full" />
                    <div className="absolute -bottom-8 -left-8 w-32 h-32 bg-white/5 rounded-full" />
                </div>

                {/* ── GIT CONFIGURATION WARNING (MOVED TO TOP) ── */}
                {!['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode) && globalGitRepoUrl && !globalGitToken && !hasSavedGlobalGitToken && (
                    <div className="mb-6 p-4 rounded-lg border border-yellow-500/50 bg-yellow-500/10 shadow-md">
                        <div className="flex items-start gap-3">
                            <AlertTriangle className="w-5 h-5 text-yellow-500 mt-0.5 flex-shrink-0" />
                            <div className="text-sm text-dark-200 flex-1">
                                <p className="font-bold mb-1.5 text-base flex items-center gap-2">
                                    <span className="text-lg">ℹ️</span> No PAT Provided
                                </p>
                                <p className="leading-snug">
                                    You haven't entered a Personal Access Token. This is required for pushing the code.
                                </p>
                            </div>
                        </div>
                    </div>
                )}

                {/* ── PROGRESS BAR (mobile) ── */}
                <div className="sm:hidden mb-4">
                    <div className="flex items-center justify-between text-xs mb-1.5">
                        <span className="font-bold text-app-primary">{providedCount} of {totalItems} confirmed</span>
                        <span className="text-app-text-light font-semibold">{progress}%</span>
                    </div>
                    <div className="w-full bg-app-bg-hover rounded-full h-2 overflow-hidden">
                        <div
                            className="bg-gradient-to-r from-amber-400 to-app-status-warning h-full rounded-full transition-all duration-500 ease-out"
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                </div>

                {/* ── EXECUTION MODE (Grid View) ── */}
                <div className="bg-app-bg-card/90 backdrop-blur-xl rounded-2xl shadow-sm border border-app-border-light/80 p-6 mb-6">
                    <h3 className="text-base font-bold text-app-text-main mb-1">Choose Execution Mode</h3>
                    <p className="text-sm text-app-text-muted mb-4">Select how this project should run in Status Dashboard.</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {PROCESS_MODE_OPTIONS.map(option => (
                            <button
                                key={option.id}
                                type="button"
                                disabled={!option.enabled}
                                onClick={() => setProcessMode(option.id)}
                                className={`text-left rounded-xl border p-4 transition-all ${processMode === option.id && option.enabled
                                    ? 'border-app-primary bg-app-primary-light shadow-sm ring-1 ring-app-primary'
                                    : option.enabled
                                        ? 'border-app-border bg-app-bg-card hover:bg-app-bg-page hover:border-indigo-300'
                                        : 'border-app-border bg-app-bg-page text-app-text-light cursor-not-allowed'
                                    }`}
                            >
                                <div className="flex items-center justify-between gap-2 mb-1.5">
                                    <p className={`text-sm font-bold ${option.enabled ? (processMode === option.id ? 'text-app-primary-dark' : 'text-app-text-main') : 'text-app-text-muted'}`}>
                                        {option.title}
                                        {option.id === recommendedMode && (
                                            <span className="ml-1.5 text-[9px] font-bold uppercase tracking-wide text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded-full">
                                                Recommended
                                            </span>
                                        )}
                                    </p>
                                    {!option.enabled && (
                                        <span className="text-[9px] font-bold uppercase tracking-wide text-app-text-muted bg-app-bg-hover px-2 py-0.5 rounded-full">
                                            Disabled
                                        </span>
                                    )}
                                    {processMode === option.id && option.enabled && (
                                        <CheckCircle2 className="w-4 h-4 text-app-primary" />
                                    )}
                                </div>
                                <p className={`text-xs ${processMode === option.id && option.enabled ? 'text-app-primary-hover' : 'text-app-text-muted'}`}>
                                    {option.description}
                                </p>
                            </button>
                        ))}
                    </div>
                </div>


                {/* ── INFO TIP ── */}
                <div className="bg-app-primary-light/80 rounded-xl border border-app-primary-ring/60 p-4 mb-6 flex items-start gap-3">
                    <Info className="w-5 h-5 text-app-primary flex-shrink-0 mt-0.5" />
                    <div>
                        <p className="text-sm font-semibold text-app-primary-dark mb-0.5">How this works</p>
                        <p className="text-xs text-app-text-main leading-relaxed">
                            {['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode)
                                ? `In ${processMode === 'vibe_coding' ? 'Vibe Coding' : processMode === 'ai_assist' ? 'AI Assist' : 'Developer Only'} mode, prerequisite classification is not required. You can proceed directly to VibeCoding workspace where you will work in the designated workflow.`
                                : 'Our AI has analyzed your BRD and identified the services, credentials, and infrastructure you\'ll need. Each prerequisite asks for the expected answer type (text, URL, or file upload).'
                            }
                        </p>
                    </div>
                </div>

                {/* ── PREREQUISITES SECTION ── */}
                {['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode) ? (
                    <div className="bg-app-bg-card/90 backdrop-blur-xl rounded-2xl shadow-sm border border-app-border-light/80 p-8 text-center mb-8 border-dashed border-app-primary-ring">
                        <div className="w-16 h-16 mx-auto mb-4 bg-app-primary-light rounded-full flex items-center justify-center">
                            <ArrowRight className="w-8 h-8 text-app-primary" />
                        </div>
                        <h3 className="text-lg font-bold text-app-text-main mb-2">
                            {processMode === 'vibe_coding' ? 'Vibe Coding Workflow' : processMode === 'ai_assist' ? 'AI Assist Workflow' : 'Developer Workflow'}
                        </h3>
                        <p className="text-sm text-app-text-label max-w-lg mx-auto leading-relaxed">
                            {processMode === 'vibe_coding'
                                ? <>Prerequisite classification is bypassed for <strong>Vibe Coding</strong> mode. You will be redirected to the VibeCoding web workspace where the AI will automatically analyze your BRD and start building your application.</>
                                : processMode === 'ai_assist'
                                    ? <>Prerequisite classification is bypassed for <strong>AI Assist</strong> mode. You will be redirected to VibeCoding workspace with AI guidance for development.</>
                                    : <>Prerequisite classification is bypassed for <strong>Developer Only</strong> mode. You will be redirected to VibeCoding workspace for manual development.</>
                            }
                        </p>
                    </div>
                ) : (
                    /* ── CATEGORY GROUPS ── */
                    <div className="space-y-5 mb-8">
                        {Object.entries(grouped).map(([category, items]) => {
                            const config = CATEGORY_CONFIG[category] || CATEGORY_CONFIG.other;
                            const CategoryIcon = config.icon;
                            const catProvided = items.filter(i => i.provided).length;

                            return (
                                <div key={category} className="bg-app-bg-card/90 backdrop-blur-xl rounded-2xl shadow-sm border border-app-border-light/80 overflow-hidden">
                                    {/* Category Header */}
                                    <div className={`flex items-center justify-between px-5 py-3.5 ${config.bg} border-b ${config.border}`}>
                                        <div className="flex items-center gap-3">
                                            <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${config.gradient} flex items-center justify-center shadow-sm`}>
                                                <CategoryIcon className="w-4 h-4 text-app-bg-card" />
                                            </div>
                                            <div>
                                                <h3 className={`text-sm font-bold ${config.text}`}>{config.label}</h3>
                                                <p className="text-[11px] text-app-text-muted">{catProvided}/{items.length} confirmed</p>
                                            </div>
                                        </div>
                                        <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full ${config.badge}`}>
                                            {items.length} {items.length === 1 ? 'item' : 'items'}
                                        </span>
                                    </div>

                                    {/* Items */}
                                    <div className="divide-y divide-app-bg-muted">
                                        {items.map(item => (
                                            <div
                                                key={item.id}
                                                className={`px-5 py-4 flex items-start gap-4 transition-all duration-200 ${item.provided ? 'bg-app-status-successBg/40' : 'hover:bg-app-bg-page/50'
                                                    }`}
                                            >
                                                {/* Checkbox */}
                                                <button
                                                    onClick={() => toggleProvided(item.id)}
                                                    className="flex-shrink-0 mt-0.5 transition-transform active:scale-90"
                                                    title={item.provided ? 'Mark as not provided' : 'Mark as provided'}
                                                >
                                                    {item.provided ? (
                                                        <CheckCircle2 className="w-6 h-6 text-app-status-success drop-shadow-sm" />
                                                    ) : (
                                                        <Circle className="w-6 h-6 text-app-border hover:text-app-text-light" />
                                                    )}
                                                </button>

                                                {/* Content */}
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center justify-between gap-2 mb-1 flex-wrap">
                                                        <div className="flex items-center gap-2">
                                                            <span className={`text-sm font-semibold ${item.provided ? 'text-app-text-muted' : 'text-app-text-main'}`}>
                                                                {item.name}
                                                            </span>
                                                            <PriorityBadge priority={item.priority} />
                                                        </div>
                                                        {/* Secret flag toggle - moved to right side */}
                                                        <button
                                                            type="button"
                                                            onClick={() => toggleSecret(item.id)}
                                                            className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium transition-colors ${item.containsSecret
                                                                ? 'border-red-200 bg-app-status-errorBg text-app-status-error'
                                                                : 'border-app-border bg-app-bg-page text-app-text-label hover:bg-app-bg-muted'
                                                                }`}
                                                            title="Mark as sensitive (will be excluded from AI payload)"
                                                        >
                                                            {item.containsSecret ? (
                                                                <CheckCircle2 className="w-3.5 h-3.5 text-app-status-error" />
                                                            ) : (
                                                                <Circle className="w-3.5 h-3.5 text-app-text-light" />
                                                            )}
                                                            Sensitive
                                                        </button>
                                                    </div>
                                                    <p className="text-xs text-app-text-muted leading-relaxed mb-2.5 max-w-2xl">
                                                        {item.description}
                                                    </p>

                                                    {/* Field type specific input */}
                                                    {item.fieldType === 'text' && (
                                                        <div className="mt-2">
                                                            <p className="text-[11px] uppercase tracking-wide text-app-text-muted mb-1.5">Expected input: Text</p>
                                                            <input
                                                                type={item.containsSecret ? "password" : "text"}
                                                                placeholder="Type your answer"
                                                                value={item.userValue || ''}
                                                                onChange={(e) => updateValue(item.id, e.target.value)}
                                                                className="w-full text-sm bg-app-bg-page border border-app-border rounded-lg px-3 py-2 focus:ring-2 focus:ring-app-primary-light focus:border-blue-300 transition-all"
                                                            />
                                                        </div>
                                                    )}
                                                    {item.fieldType === 'url' && (
                                                        <div className="mt-2">
                                                            <p className="text-[11px] uppercase tracking-wide text-app-text-muted mb-1.5">Expected input: URL</p>
                                                            <input
                                                                type={item.containsSecret ? "password" : "url"}
                                                                placeholder="https://example.com"
                                                                value={item.userValue || ''}
                                                                onChange={(e) => updateValue(item.id, e.target.value)}
                                                                className="w-full text-sm bg-app-bg-page border border-app-border rounded-lg px-3 py-2 focus:ring-2 focus:ring-app-primary-light focus:border-blue-300 transition-all"
                                                            />
                                                        </div>
                                                    )}
                                                    {item.fieldType === 'file' && (
                                                        <div className="mt-2">
                                                            <p className="text-[11px] uppercase tracking-wide text-app-text-muted mb-1.5">Expected input: File upload</p>
                                                            <input
                                                                type="file"
                                                                onChange={(e) => updateFile(item.id, e.target.files[0])}
                                                                className="w-full text-sm"
                                                            />
                                                            {item.userFileName && (
                                                                <div className="mt-2 flex items-center gap-2">
                                                                    <span className="text-xs text-app-text-label">Selected: {item.userFileName}</span>
                                                                    <button
                                                                        type="button"
                                                                        onClick={() => updateFile(item.id, null)}
                                                                        className="text-[11px] text-app-status-error hover:text-app-status-error font-medium"
                                                                    >
                                                                        Remove
                                                                    </button>
                                                                </div>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* ── CUSTOM RULES SECTION ── */}
                {!['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode) && (
                    <div className="bg-app-bg-card/90 backdrop-blur-xl rounded-2xl shadow-sm border border-app-border-light/80 p-6 mb-6 space-y-4">
                        <div className="flex items-center gap-2 mb-1">
                            <div className="w-8 h-8 rounded-lg bg-app-primary-light flex items-center justify-center">
                                <Sparkles className="w-4 h-4 text-app-primary" />
                            </div>
                            <h3 className="text-base font-bold text-app-text-main">A.I. Custom Rules</h3>
                        </div>
                        <p className="text-sm text-app-text-muted">
                            Define specific coding standards, architectural patterns, or task constraints. The AI will follow these instructions when generating the project plan and tasks.
                        </p>
                        <textarea
                            value={customRules}
                            onChange={(e) => setCustomRules(e.target.value)}
                            placeholder="e.g. Use functional components for React, follow SOLID principles, all API tasks must include error handling documentation..."
                            className="w-full min-h-[120px] p-4 text-sm text-app-text-main bg-app-bg-page border border-app-border rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-indigo-400 transition-all outline-none resize-y"
                        />
                        <div className="flex items-center gap-2 text-[11px] text-app-primary font-medium bg-app-primary-light/50 px-3 py-2 rounded-lg italic">
                            <AlertCircle className="w-3.5 h-3.5" />
                            Rules are saved automatically for this project.
                        </div>
                    </div>
                )}

                {/* ── AI CONTEXT FILES UPLOAD SECTION ── */}
                <div className="bg-app-bg-card/90 backdrop-blur-xl rounded-2xl shadow-sm border border-app-border-light/80 p-6 mb-6 space-y-4">
                    <div className="flex items-center gap-2 mb-1">
                        <div className="w-8 h-8 rounded-lg bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center">
                            <FileKey className="w-4 h-4 text-violet-600 dark:text-violet-400" />
                        </div>
                        <h3 className="text-base font-bold text-app-text-main">AI Operational Directives</h3>
                    </div>
                    <p className="text-sm text-app-text-muted">
                        Upload markdown files that contain project context, guidelines, or documentation. These files will be available for reference during development.
                    </p>
                    
                    {/* Upload Button */}
                    <div className="flex items-center gap-3">
                        <label className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-violet-500 to-purple-600 rounded-lg hover:shadow-lg transition-all cursor-pointer">
                            <Package className="w-4 h-4" />
                            Upload Context Files
                            <input
                                type="file"
                                accept=".md"
                                multiple
                                onChange={handleClaudeMdUpload}
                                className="hidden"
                            />
                        </label>
                        <span className="text-xs text-app-text-muted">
                            {claudeMdFiles.length > 0 ? `${claudeMdFiles.length} file${claudeMdFiles.length !== 1 ? 's' : ''} uploaded` : 'No files uploaded yet'}
                        </span>
                    </div>
                    
                    {/* Uploaded Files List */}
                    {claudeMdFiles.length > 0 && (
                        <div className="space-y-2 mt-4">
                            <p className="text-xs font-semibold text-app-text-label uppercase tracking-wider">Uploaded Files</p>
                            <div className="space-y-2">
                                {claudeMdFiles.map((file, index) => (
                                    <div
                                        key={index}
                                        className="flex items-center justify-between p-3 bg-app-bg-page border border-app-border rounded-lg hover:bg-app-bg-hover transition-colors"
                                    >
                                        <div className="flex items-center gap-3 flex-1 min-w-0">
                                            <FileKey className="w-4 h-4 text-violet-600 dark:text-violet-400 flex-shrink-0" />
                                            <div className="flex-1 min-w-0">
                                                <p className="text-sm font-semibold text-app-text-main truncate">{file.name}</p>
                                                <p className="text-xs text-app-text-muted">
                                                    Uploaded {new Date(file.uploadedAt).toLocaleDateString()} at {new Date(file.uploadedAt).toLocaleTimeString()}
                                                </p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2 flex-shrink-0">
                                            <button
                                                onClick={() => handleViewClaudeMd(file)}
                                                className="px-3 py-1.5 text-xs font-semibold text-violet-600 dark:text-violet-400 hover:bg-violet-100 dark:hover:bg-violet-900/30 rounded-md transition-colors"
                                            >
                                                View
                                            </button>
                                            <button
                                                onClick={() => handleRemoveClaudeMd(file.name)}
                                                className="px-3 py-1.5 text-xs font-semibold text-app-status-error hover:bg-app-status-errorBg rounded-md transition-colors"
                                            >
                                                Remove
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                    
                    <div className="flex items-center gap-2 text-[11px] text-violet-600 dark:text-violet-400 font-medium bg-violet-100 dark:bg-violet-900/30 px-3 py-2 rounded-lg italic">
                        <Info className="w-3.5 h-3.5" />
                        Context files are saved per project and can be referenced during development.
                    </div>
                </div>

                {/* ── SKILLS.MD UPLOAD SECTION ── */}
                <div className="bg-app-bg-card/90 backdrop-blur-xl rounded-2xl shadow-sm border border-app-border-light/80 p-6 mb-6 space-y-4">
                    <div className="flex items-center gap-2 mb-1">
                        <div className="w-8 h-8 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
                            <Sparkles className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                        </div>
                        <h3 className="text-base font-bold text-app-text-main">Cognitive Skill Modules</h3>
                    </div>
                    <p className="text-sm text-app-text-muted">
                        Upload reusable markdown modules files that define agent capabilities, coding standards, or specialized knowledge. Each skill can be referenced by agents during task execution.
                    </p>
                    
                    {/* Upload Button */}
                    <div className="flex items-center gap-3">
                        <label className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-emerald-500 to-teal-600 rounded-lg hover:shadow-lg transition-all cursor-pointer">
                            <Sparkles className="w-4 h-4" />
                            Upload Skills.md
                            <input
                                type="file"
                                accept=".md"
                                multiple
                                onChange={handleSkillsMdUpload}
                                className="hidden"
                            />
                        </label>
                        <span className="text-xs text-app-text-muted">
                            {skillsMdFiles.length > 0 ? `${skillsMdFiles.length} skill${skillsMdFiles.length !== 1 ? 's' : ''} uploaded` : 'No skills uploaded yet'}
                        </span>
                    </div>
                    
                    {/* Uploaded Files List */}
                    {skillsMdFiles.length > 0 && (
                        <div className="space-y-2 mt-4">
                            <p className="text-xs font-semibold text-app-text-label uppercase tracking-wider">Uploaded Skills</p>
                            <div className="space-y-2">
                                {skillsMdFiles.map((file, index) => (
                                    <div
                                        key={index}
                                        className="flex items-center justify-between p-3 bg-app-bg-page border border-app-border rounded-lg hover:bg-app-bg-hover transition-colors"
                                    >
                                        <div className="flex items-center gap-3 flex-1 min-w-0">
                                            <Sparkles className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
                                            <div className="flex-1 min-w-0">
                                                <p className="text-sm font-semibold text-app-text-main truncate">{file.name}</p>
                                                <p className="text-xs text-app-text-muted">
                                                    Uploaded {new Date(file.uploadedAt).toLocaleDateString()} at {new Date(file.uploadedAt).toLocaleTimeString()}
                                                </p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2 flex-shrink-0">
                                            <button
                                                onClick={() => handleViewSkillsMd(file)}
                                                className="px-3 py-1.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100 dark:hover:bg-emerald-900/30 rounded-md transition-colors"
                                            >
                                                View
                                            </button>
                                            <button
                                                onClick={() => handleRemoveSkillsMd(file.name)}
                                                className="px-3 py-1.5 text-xs font-semibold text-app-status-error hover:bg-app-status-errorBg rounded-md transition-colors"
                                            >
                                                Remove
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                    
                    <div className="flex items-center gap-2 text-[11px] text-emerald-600 dark:text-emerald-400 font-medium bg-emerald-100 dark:bg-emerald-900/30 px-3 py-2 rounded-lg italic">
                        <Info className="w-3.5 h-3.5" />
                        Skills.md files are saved per project and define specialized capabilities for agents.
                    </div>
                </div>

                {/* ── AI CONTEXT FILE VIEWER MODAL ── */}
                {showClaudeMdViewer && (
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[9999] p-4">
                        <div className="bg-app-bg-card rounded-2xl shadow-2xl border border-app-border max-w-4xl w-full max-h-[80vh] flex flex-col">
                            {/* Modal Header */}
                            <div className="flex items-center justify-between p-6 border-b border-app-border">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-xl bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center">
                                        <FileKey className="w-5 h-5 text-violet-600 dark:text-violet-400" />
                                    </div>
                                    <div>
                                        <h3 className="text-lg font-bold text-app-text-main">{selectedClaudeMdName}</h3>
                                        <p className="text-xs text-app-text-muted">Context File Viewer</p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => setShowClaudeMdViewer(false)}
                                    className="w-8 h-8 rounded-lg hover:bg-app-bg-hover flex items-center justify-center transition-colors"
                                >
                                    <span className="text-xl text-app-text-muted">×</span>
                                </button>
                            </div>
                            
                            {/* Modal Content */}
                            <div className="flex-1 overflow-y-auto p-6">
                                <pre className="text-sm text-app-text-main bg-app-bg-page p-4 rounded-lg border border-app-border whitespace-pre-wrap break-words font-mono">
                                    {selectedClaudeMdContent}
                                </pre>
                            </div>
                            
                            {/* Modal Footer */}
                            <div className="flex items-center justify-end gap-3 p-6 border-t border-app-border">
                                <button
                                    onClick={() => setShowClaudeMdViewer(false)}
                                    className="px-4 py-2.5 text-sm font-semibold text-app-text-main bg-app-bg-page border border-app-border rounded-lg hover:bg-app-bg-hover transition-colors"
                                >
                                    Close
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* ── SKILLS.MD VIEWER MODAL ── */}
                {showSkillsMdViewer && (
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[9999] p-4">
                        <div className="bg-app-bg-card rounded-2xl shadow-2xl border border-app-border max-w-4xl w-full max-h-[80vh] flex flex-col">
                            {/* Modal Header */}
                            <div className="flex items-center justify-between p-6 border-b border-app-border">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
                                        <Sparkles className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                                    </div>
                                    <div>
                                        <h3 className="text-lg font-bold text-app-text-main">{selectedSkillsMdName}</h3>
                                        <p className="text-xs text-app-text-muted">Skills.md File Viewer</p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => setShowSkillsMdViewer(false)}
                                    className="w-8 h-8 rounded-lg hover:bg-app-bg-hover flex items-center justify-center transition-colors"
                                >
                                    <span className="text-xl text-app-text-muted">×</span>
                                </button>
                            </div>
                            
                            {/* Modal Content */}
                            <div className="flex-1 overflow-y-auto p-6">
                                <pre className="text-sm text-app-text-main bg-app-bg-page p-4 rounded-lg border border-app-border whitespace-pre-wrap break-words font-mono">
                                    {selectedSkillsMdContent}
                                </pre>
                            </div>
                            
                            {/* Modal Footer */}
                            <div className="flex items-center justify-end gap-3 p-6 border-t border-app-border">
                                <button
                                    onClick={() => setShowSkillsMdViewer(false)}
                                    className="px-4 py-2.5 text-sm font-semibold text-app-text-main bg-app-bg-page border border-app-border rounded-lg hover:bg-app-bg-hover transition-colors"
                                >
                                    Close
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* ── SUMMARY + SUBMIT ── */}
                <div className="bg-app-bg-card/90 backdrop-blur-xl rounded-2xl shadow-lg border border-app-border-light/80 p-6 mb-6">
                    {!['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode) && (
                        <div className="mb-6 pb-6 border-b border-app-border-light">
                            <div className="flex items-center gap-2 mb-1 flex-wrap">
                                <h3 className="text-base font-bold text-app-text-main">Git Configuration</h3>
                                <span className={`text-[10px] font-extrabold px-2.5 py-0.5 rounded-full border uppercase tracking-wider ${
                                    (projectType || '').toLowerCase() === 'brownfield'
                                        ? 'bg-amber-500/10 text-amber-700 border-amber-300 dark:border-amber-700 dark:text-amber-300'
                                        : (projectType || '').toLowerCase() === 'migration' || (projectType || '').toLowerCase() === 'modernization'
                                        ? 'bg-blue-500/10 text-blue-700 border-blue-300 dark:border-blue-700 dark:text-blue-300'
                                        : 'bg-emerald-500/10 text-emerald-700 border-emerald-300 dark:border-emerald-700 dark:text-emerald-300'
                                }`}>
                                    {(projectType || 'greenfield').toUpperCase()} APP
                                </span>
                            </div>
                            <p className="text-sm text-app-text-muted mb-4">
                                Provide one global repository (GitHub or Azure DevOps) here. All agents in this project will use these credentials. PAT is optional for public repositories.
                            </p>

                            {(!globalGitRepoUrl || !globalGitRepoUrl.trim()) ? (
                                <div className="mb-4 rounded-xl border border-amber-300 dark:border-amber-700/80 bg-amber-500/10 dark:bg-amber-950/40 p-4 flex items-start gap-3">
                                    <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
                                    <div>
                                        <p className="text-sm font-extrabold text-amber-900 dark:text-amber-100">No git repository configured</p>
                                        <p className="text-xs font-medium text-amber-800 dark:text-amber-200 mt-1 leading-relaxed">
                                            This project has no Git repository settings saved. Please enter a repository URL below.
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <div className="mb-4 rounded-xl border border-emerald-300 dark:border-emerald-700/80 bg-emerald-500/10 dark:bg-emerald-950/40 p-4 flex items-start gap-3">
                                    <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 mt-0.5 flex-shrink-0" />
                                    <div>
                                        <p className="text-sm font-extrabold text-emerald-900 dark:text-emerald-100">Git repository configured</p>
                                        <p className="text-xs font-medium text-emerald-800 dark:text-emerald-200 mt-1 leading-relaxed">
                                            Current repository: <span className="font-mono font-bold break-all">{globalGitRepoUrl}</span>
                                        </p>
                                    </div>
                                </div>
                            )}
                            
                            {shouldShowRepoSuggestion && (
                                <div className="mb-4 rounded-xl border border-app-primary-ring bg-app-primary-light/80 p-4">
                                    <p className="text-sm font-semibold text-app-primary-dark">Repository detected from analysis</p>
                                    <p className="text-xs text-app-primary-hover mt-1">
                                        Using <span className="font-semibold">{analysisRepoSuggestion.repo}</span>
                                        {analysisRepoSuggestion.branch ? ` (${analysisRepoSuggestion.branch})` : ''} from BRD section for this project.
                                        You can change it below if needed.
                                    </p>
                                </div>
                            )}
                            <div className="grid grid-cols-1 gap-4">
                                <div>
                                    <div className="mb-2 inline-flex rounded-lg border border-app-border p-1 bg-app-bg-page/60">
                                        <button
                                            type="button"
                                            onClick={() => setRepoProvider('github')}
                                            className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${repoProvider === 'github'
                                                ? 'bg-app-primary text-white'
                                                : 'text-app-text-muted hover:text-app-text-label'
                                                }`}
                                        >
                                            GitHub / Git
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setRepoProvider('azure-devops')}
                                            className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${repoProvider === 'azure-devops'
                                                ? 'bg-app-primary text-white'
                                                : 'text-app-text-muted hover:text-app-text-label'
                                                }`}
                                        >
                                            Azure DevOps
                                        </button>
                                    </div>
                                    <label className="block text-[11px] font-bold text-app-text-label mb-2 uppercase tracking-widest">
                                        Repository URL <span className="text-app-status-error">*</span>
                                    </label>
                                    <input
                                        type="text"
                                        value={globalGitRepoUrl}
                                        onChange={(e) => {
                                            setGlobalGitRepoUrl(e.target.value);
                                            // Clear validation when URL changes
                                            setGitValidationResult(null);
                                            setGitValidationError('');
                                        }}
                                        placeholder={repoProvider === 'azure-devops'
                                            ? 'https://dev.azure.com/ORG/PROJECT/_git/REPO'
                                            : 'https://github.com/org/repo.git'
                                        }
                                        className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-blue-400 text-sm bg-app-bg-card text-app-text-main transition-all duration-200"
                                    />
                                    
                                    {/* Validation Result */}
                                    {gitValidationResult && (
                                        <div className="mt-3 p-3 rounded-lg border border-emerald-200 bg-emerald-50 dark:bg-emerald-900/20 dark:border-emerald-800">
                                            <div className="flex items-start gap-2">
                                                <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 mt-0.5 flex-shrink-0" />
                                                <div className="flex-1 min-w-0">
                                                    <p className="text-sm font-semibold text-emerald-700 dark:text-dark-300">
                                                        {gitValidationResult.message}
                                                    </p>
                                                    {gitValidationResult.normalized_url && gitValidationResult.normalized_url !== globalGitRepoUrl && (
                                                        <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                                                            URL normalized to: {gitValidationResult.normalized_url}
                                                        </p>
                                                    )}
                                                    {repoProvider === 'azure-devops' && gitValidationResult.organization && (
                                                        <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                                                            Organization: {gitValidationResult.organization} | Project: {gitValidationResult.project} | Repo: {gitValidationResult.repo}
                                                        </p>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                    

                                </div>
                                <div>
                                    <label className="block text-[11px] font-bold text-app-text-label mb-2 uppercase tracking-widest">
                                        Personal Access Token
                                    </label>
                                    <input
                                        type="password"
                                        value={globalGitToken}
                                        onChange={(e) => {
                                            setGlobalGitToken(e.target.value);
                                            // Clear validation when token changes
                                            setGitValidationResult(null);
                                            setGitValidationError('');
                                        }}
                                        placeholder={hasSavedGlobalGitToken ? 'Leave blank to keep existing PAT' : 'Optional for public repos (ghp_... or Azure PAT)'}
                                        className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-blue-400 text-sm bg-app-bg-card text-app-text-main transition-all duration-200"
                                    />
                                    <p className="text-xs text-app-text-muted mt-2">
                                        {hasSavedGlobalGitToken
                                            ? 'PAT already saved for this project. Enter a new one only if you want to replace it.'
                                            : repoProvider === 'azure-devops'
                                                ? 'Azure DevOps PAT with Code (Read & Write) permissions. Required for pushing code.'
                                                : 'GitHub PAT with repo scope (optional for public repos).'}
                                    </p>
                                </div>
                                
                                {/* Validate Button */}
                                <div>
                                    <button
                                        type="button"
                                        onClick={handleValidateGitConnection}
                                        disabled={isValidatingGit || !globalGitRepoUrl.trim()}
                                        className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-app-primary to-app-primary-hover rounded-lg hover:shadow-lg transition-all disabled:from-app-border disabled:to-app-text-light disabled:cursor-not-allowed"
                                    >
                                        {isValidatingGit ? (
                                            <>
                                                <Loader2 className="w-4 h-4 animate-spin" />
                                                Validating...
                                            </>
                                        ) : (
                                            <>
                                                <CheckCircle2 className="w-4 h-4" />
                                                Test Connection
                                            </>
                                        )}
                                    </button>
                                    <p className="text-xs text-app-text-muted mt-2">
                                        Click to verify the repository URL and PAT are correct before proceeding.
                                    </p>
                                </div>
                                
                                {isLoadingGitConfig && (
                                    <p className="text-xs text-app-text-muted">Loading saved Git config...</p>
                                )}

                                {isInspectingRepo && (
                                    <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400 mt-2">
                                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                        <span>Inspecting repository files for Greenfield compatibility...</span>
                                    </div>
                                )}

                                {greenfieldAction && (
                                    <div className={`mt-4 p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm ${
                                        greenfieldAction === 'wipe'
                                            ? 'bg-amber-500/10 border-amber-300 dark:border-amber-700/80 text-amber-900 dark:text-amber-100'
                                            : greenfieldAction === 'custom'
                                                ? 'bg-purple-500/10 border-purple-300 dark:border-purple-700/80 text-purple-900 dark:text-purple-100'
                                                : 'bg-emerald-500/10 border-emerald-300 dark:border-emerald-700/80 text-emerald-900 dark:text-emerald-100'
                                    }`}>
                                        <div className="flex items-start gap-3 min-w-0">
                                            {greenfieldAction === 'wipe' ? (
                                                <div className="w-8 h-8 rounded-lg bg-amber-200 dark:bg-amber-900/50 flex items-center justify-center flex-shrink-0 text-amber-700 dark:text-amber-300">
                                                    <Trash2 className="w-4 h-4" />
                                                </div>
                                            ) : greenfieldAction === 'custom' ? (
                                                <div className="w-8 h-8 rounded-lg bg-purple-200 dark:bg-purple-900/50 flex items-center justify-center flex-shrink-0 text-purple-700 dark:text-purple-300">
                                                    <FileCode className="w-4 h-4" />
                                                </div>
                                            ) : (
                                                <div className="w-8 h-8 rounded-lg bg-emerald-200 dark:bg-emerald-900/50 flex items-center justify-center flex-shrink-0 text-emerald-700 dark:text-emerald-300">
                                                    <CheckCircle2 className="w-4 h-4" />
                                                </div>
                                            )}
                                            <div className="min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <span className="text-xs font-bold uppercase tracking-wider">
                                                        {greenfieldAction === 'wipe' && 'Greenfield Strategy: Clean Slate'}
                                                        {greenfieldAction === 'custom' && 'Greenfield Strategy: Custom Directive'}
                                                        {greenfieldAction === 'new_repo' && 'Greenfield Strategy: New Clean Repository'}
                                                    </span>
                                                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-black/10 dark:bg-white/10">Active</span>
                                                </div>
                                                <p className="text-xs font-medium mt-0.5 opacity-90 leading-relaxed">
                                                    {greenfieldAction === 'wipe' && 'The AI agents will clean out pre-existing repository code and start brand new from the BRD requirements.'}
                                                    {greenfieldAction === 'custom' && (greenfieldCustomInstructions ? `"${greenfieldCustomInstructions}"` : 'Custom user instructions will govern pre-existing code.')}
                                                    {greenfieldAction === 'new_repo' && 'Agents will build in the clean replacement repository.'}
                                                </p>
                                            </div>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setModalActionChoice(greenfieldAction || 'wipe');
                                                setModalCustomInstructions(greenfieldCustomInstructions || '');
                                                setShowGreenfieldModal(true);
                                            }}
                                            className="px-3 py-1.5 text-xs font-bold rounded-lg border border-current hover:bg-black/5 dark:hover:bg-white/5 transition-colors self-start sm:self-center flex-shrink-0"
                                        >
                                            Change Strategy
                                        </button>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                        <div>
                            <h3 className="text-base font-bold text-app-text-main mb-1">Ready to proceed?</h3>
                            <p className="text-sm text-app-text-muted">
                                {['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode)
                                    ? '🚀 You will be redirected to VibeCoding workspace to start development.'
                                    : allProvided
                                        ? '✅ All prerequisites confirmed. You can proceed to task creation.'
                                        : `${totalItems - providedCount} item${totalItems - providedCount !== 1 ? 's' : ''} still pending. You can still proceed, but ensure all items are addressed before agent execution.`
                                }
                            </p>
                        </div>

                        <button
                            onClick={handleSubmit}
                            disabled={submitting || isLoadingGitConfig || !isGlobalGitConfigValid}
                            className={`inline-flex items-center gap-2 py-3 px-7 text-sm font-bold rounded-xl text-app-bg-card transition-all shadow-lg active:scale-[0.97] flex-shrink-0 ${allProvided
                                ? 'bg-gradient-to-r from-app-status-success to-teal-600 hover:from-app-status-success hover:to-teal-700 shadow-emerald-200/50'
                                : 'bg-gradient-to-r from-app-primary to-app-primary hover:from-app-primary-hover hover:to-app-primary-hover shadow-app-primary-ring/50'
                                } disabled:from-app-border disabled:to-app-text-light disabled:cursor-not-allowed disabled:shadow-none`}
                        >
                            {submitting ? (
                                <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</>
                            ) : (
                                <>{(allProvided || ['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode)) ? <CheckCircle2 className="w-4 h-4" /> : <ArrowRight className="w-4 h-4" />}
                                    {['developer_only', 'ai_assist', 'vibe_coding'].includes(processMode) ? 'Open VibeCoding' : (allProvided ? 'Confirm & Proceed' : 'Proceed Anyway')}</>
                            )}
                        </button>
                    </div>
                </div>
            </div>

            {/* Greenfield Non-Empty Repository Modal */}
            {showGreenfieldModal && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-[9999] p-3 sm:p-4 overflow-y-auto">
                    <div className="bg-app-bg-card rounded-2xl shadow-2xl border border-amber-300 dark:border-amber-700 max-w-lg w-full my-auto flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                        {/* Glow Banner */}
                        <div className="h-1 bg-gradient-to-r from-amber-500 via-orange-500 to-amber-500" />

                        {/* Modal Header */}
                        <div className="px-5 py-3.5 border-b border-app-border-light bg-gradient-to-b from-amber-500/10 to-transparent">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-300 dark:border-amber-700 flex items-center justify-center flex-shrink-0 text-amber-600 dark:text-amber-400">
                                    <AlertTriangle className="w-4 h-4" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <h3 className="text-sm sm:text-base font-extrabold text-app-text-main truncate">
                                            Greenfield: Existing Code Detected
                                        </h3>
                                        <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-800 dark:text-amber-300 uppercase tracking-wider flex-shrink-0">
                                            Action Required
                                        </span>
                                    </div>
                                    <p className="text-[11px] text-app-text-muted mt-0.5 truncate">
                                        Marked as <strong>Greenfield</strong>, but the repository already contains code.
                                    </p>
                                </div>
                            </div>

                            {/* Compact Inspection Details Strip */}
                            <div className="mt-2.5 px-3 py-1.5 rounded-lg bg-app-bg-page border border-app-border flex items-center justify-between text-[11px] gap-2 flex-wrap">
                                <div className="flex items-center gap-2 min-w-0 flex-1">
                                    <span className="font-mono text-app-text-main font-semibold truncate max-w-[220px]" title={globalGitRepoUrl}>
                                        {globalGitRepoUrl.replace('https://github.com/', '').replace('https://dev.azure.com/', '')}
                                    </span>
                                    <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-700 dark:text-amber-300 font-bold text-[10px] whitespace-nowrap">
                                        {greenfieldRepoDetails?.total_files || 'Multiple'} files
                                    </span>
                                </div>
                                {greenfieldRepoDetails?.top_level_items && greenfieldRepoDetails.top_level_items.length > 0 && (
                                    <div className="flex items-center gap-1 overflow-x-auto text-[10px] font-mono">
                                        {greenfieldRepoDetails.top_level_items.slice(0, 4).map((item, idx) => (
                                            <span key={idx} className="px-1.5 py-0.5 rounded bg-app-bg-card border border-app-border text-app-text-muted whitespace-nowrap">
                                                {item.type === 'directory' ? '📁' : '📄'} {item.name}
                                            </span>
                                        ))}
                                        {greenfieldRepoDetails.top_level_items.length > 4 && (
                                            <span className="text-app-text-muted text-[10px]">+{greenfieldRepoDetails.top_level_items.length - 4} more</span>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Modal Body: Strategy Selection */}
                        <div className="px-5 py-3 space-y-2 max-h-[55vh] overflow-y-auto">
                            <p className="text-[10px] font-bold uppercase tracking-wider text-app-text-label">
                                How should the AI agents proceed?
                            </p>

                            {/* Option 1: Wipe & Build Fresh */}
                            <div
                                onClick={() => setModalActionChoice('wipe')}
                                className={`p-2.5 rounded-xl border transition-all cursor-pointer relative ${
                                    modalActionChoice === 'wipe'
                                        ? 'border-amber-500 bg-amber-500/10 shadow-sm'
                                        : 'border-app-border bg-app-bg-page hover:border-amber-400/50'
                                }`}
                            >
                                <div className="flex items-start gap-2.5">
                                    <input
                                        type="radio"
                                        name="greenfield_strategy"
                                        checked={modalActionChoice === 'wipe'}
                                        onChange={() => setModalActionChoice('wipe')}
                                        className="mt-0.5 w-3.5 h-3.5 text-amber-600 focus:ring-amber-500"
                                    />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-1.5 flex-wrap">
                                            <Trash2 className="w-3.5 h-3.5 text-amber-600" />
                                            <span className="text-xs font-bold text-app-text-main">
                                                Wipe Existing Code & Build Fresh
                                            </span>
                                            <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-amber-500 text-white uppercase tracking-wider">
                                                Recommended
                                            </span>
                                        </div>
                                        <p className="text-[11px] text-app-text-muted mt-0.5 leading-snug">
                                            Clean out existing code (preserves Git remote) and build fresh from BRD requirements.
                                        </p>
                                    </div>
                                </div>
                            </div>

                            {/* Option 2: Provide a Different (Empty) Repository */}
                            <div
                                onClick={() => setModalActionChoice('new_repo')}
                                className={`p-2.5 rounded-xl border transition-all cursor-pointer relative ${
                                    modalActionChoice === 'new_repo'
                                        ? 'border-sky-500 bg-sky-500/10 shadow-sm'
                                        : 'border-app-border bg-app-bg-page hover:border-sky-400/50'
                                }`}
                            >
                                <div className="flex items-start gap-2.5">
                                    <input
                                        type="radio"
                                        name="greenfield_strategy"
                                        checked={modalActionChoice === 'new_repo'}
                                        onChange={() => setModalActionChoice('new_repo')}
                                        className="mt-0.5 w-3.5 h-3.5 text-sky-600 focus:ring-sky-500"
                                    />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-1.5">
                                            <FolderGit2 className="w-3.5 h-3.5 text-sky-600" />
                                            <span className="text-xs font-bold text-app-text-main">
                                                Provide a Different (Empty) Repository
                                            </span>
                                        </div>
                                        <p className="text-[11px] text-app-text-muted mt-0.5 leading-snug">
                                            Connect a clean, empty repository URL for this greenfield project.
                                        </p>

                                        {modalActionChoice === 'new_repo' && (
                                            <div className="mt-2 space-y-2 pt-2 border-t border-sky-200 dark:border-sky-900/50" onClick={(e) => e.stopPropagation()}>
                                                <div>
                                                    <input
                                                        type="text"
                                                        value={modalNewRepoUrl}
                                                        onChange={(e) => setModalNewRepoUrl(e.target.value)}
                                                        placeholder="https://github.com/org/empty-repo.git"
                                                        className="w-full text-xs px-2.5 py-1.5 border rounded-lg bg-app-bg-card border-app-border text-app-text-main focus:ring-2 focus:ring-sky-400 outline-none font-mono"
                                                    />
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <input
                                                        type="password"
                                                        value={modalNewRepoToken}
                                                        onChange={(e) => setModalNewRepoToken(e.target.value)}
                                                        placeholder="PAT (optional if public)"
                                                        className="flex-1 text-xs px-2.5 py-1.5 border rounded-lg bg-app-bg-card border-app-border text-app-text-main focus:ring-2 focus:ring-sky-400 outline-none"
                                                    />
                                                    <button
                                                        type="button"
                                                        onClick={handleValidateModalNewRepo}
                                                        disabled={isValidatingModalNewRepo || !modalNewRepoUrl.trim()}
                                                        className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg text-white bg-sky-600 hover:bg-sky-700 disabled:opacity-50 transition-colors whitespace-nowrap"
                                                    >
                                                        {isValidatingModalNewRepo ? (
                                                            <><Loader2 className="w-3 h-3 animate-spin" /> Verifying…</>
                                                        ) : (
                                                            <><CheckCircle2 className="w-3 h-3" /> Verify</>
                                                        )}
                                                    </button>
                                                </div>
                                                {modalNewRepoValidation && (
                                                    <p className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">
                                                        ✓ {modalNewRepoValidation.message}
                                                    </p>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Option 3: Keep Existing Code with Custom Instructions */}
                            <div
                                onClick={() => setModalActionChoice('custom')}
                                className={`p-2.5 rounded-xl border transition-all cursor-pointer relative ${
                                    modalActionChoice === 'custom'
                                        ? 'border-purple-500 bg-purple-500/10 shadow-sm'
                                        : 'border-app-border bg-app-bg-page hover:border-purple-400/50'
                                }`}
                            >
                                <div className="flex items-start gap-2.5">
                                    <input
                                        type="radio"
                                        name="greenfield_strategy"
                                        checked={modalActionChoice === 'custom'}
                                        onChange={() => setModalActionChoice('custom')}
                                        className="mt-0.5 w-3.5 h-3.5 text-purple-600 focus:ring-purple-500"
                                    />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-1.5">
                                            <FileCode className="w-3.5 h-3.5 text-purple-600" />
                                            <span className="text-xs font-bold text-app-text-main">
                                                Keep Existing Code & Give Custom Instructions
                                            </span>
                                        </div>
                                        <p className="text-[11px] text-app-text-muted mt-0.5 leading-snug">
                                            Keep current files and give custom rules on how agents handle them.
                                        </p>

                                        {modalActionChoice === 'custom' && (
                                            <div className="mt-2 pt-2 border-t border-purple-200 dark:border-purple-900/50" onClick={(e) => e.stopPropagation()}>
                                                <textarea
                                                    rows={2}
                                                    value={modalCustomInstructions}
                                                    onChange={(e) => setModalCustomInstructions(e.target.value)}
                                                    placeholder="e.g. Keep existing auth in /auth. Generate greenfield endpoints under /api/v2 and rewrite frontend..."
                                                    className="w-full text-xs p-2 border rounded-lg bg-app-bg-card border-app-border text-app-text-main focus:ring-2 focus:ring-purple-400 outline-none leading-normal"
                                                />
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {modalNewRepoError && (
                                <div className="p-2 rounded-lg bg-red-500/10 border border-red-300 dark:border-red-800 text-[11px] text-red-700 dark:text-red-300">
                                    {modalNewRepoError}
                                </div>
                            )}
                        </div>

                        {/* Modal Footer */}
                        <div className="px-5 py-2.5 border-t border-app-border bg-app-bg-page/50 flex items-center justify-end gap-2">
                            <button
                                type="button"
                                onClick={() => setShowGreenfieldModal(false)}
                                className="px-3.5 py-1.5 text-xs font-semibold rounded-lg border border-app-border hover:bg-app-bg-hover text-app-text-muted transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={handleApplyGreenfieldStrategy}
                                className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-bold rounded-lg text-white bg-gradient-to-r from-amber-600 via-orange-600 to-amber-600 hover:shadow shadow-amber-500/20 active:scale-95 transition-all"
                            >
                                <CheckCircle2 className="w-3.5 h-3.5" />
                                Apply Strategy & Proceed
                            </button>
                        </div>
                    </div>
                </div>
            )}

            
            {/* Toast / Snackbar Floating Notifications Container (Top Right - clears App Header) */}
            <div className="fixed top-20 right-6 z-[9999] flex flex-col gap-3 pointer-events-none">
                {/* General Page Error Toast */}
                {error && (
                    <div className="pointer-events-auto bg-red-600/95 backdrop-blur-md border border-red-500/50 rounded-xl shadow-2xl px-4 py-3.5 min-w-[340px] max-w-md flex items-start gap-3 animate-slide-down">
                        <AlertCircle className="w-5 h-5 text-white flex-shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-white">Repository / Action Error</p>
                            <p className="text-xs text-red-100 mt-0.5 leading-relaxed">{error}</p>
                        </div>
                        <button
                            onClick={() => setError('')}
                            className="text-red-200 hover:text-white transition-colors flex-shrink-0 p-1 rounded-md hover:bg-white/10"
                            title="Dismiss"
                        >
                            <span className="text-lg leading-none">&times;</span>
                        </button>
                    </div>
                )}

                {/* Git Validation Toast / Snackbar */}
                {gitToastVisible && gitValidationError && (
                    <div className="pointer-events-auto bg-red-600/95 backdrop-blur-md border border-red-500/50 rounded-xl shadow-2xl px-4 py-3.5 min-w-[340px] max-w-md flex items-start gap-3 animate-slide-down">
                        <AlertCircle className="w-5 h-5 text-white flex-shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-white">Repository Access Error</p>
                            <p className="text-xs text-red-100 mt-0.5 leading-relaxed">{gitValidationError}</p>
                        </div>
                        <button
                            onClick={hideGitToast}
                            className="text-red-200 hover:text-white transition-colors flex-shrink-0 p-1 rounded-md hover:bg-white/10"
                            title="Dismiss"
                        >
                            <span className="text-lg leading-none">&times;</span>
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};

export default PrerequisiteClassification;
