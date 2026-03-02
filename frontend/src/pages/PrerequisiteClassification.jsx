import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';
import {
    KeyRound, CheckCircle2, Circle, AlertCircle, ArrowRight,
    ChevronLeft, Database, Globe, Server,
    Lock, FileKey, Cloud, Package, Info, Sparkles, Loader2
} from 'lucide-react';

/* ─────────────────────────────────────────────────────────
   CATEGORY CONFIG — icon + colour for each prerequisite type
───────────────────────────────────────────────────────── */
const CATEGORY_CONFIG = {
    credentials: {
        icon: Lock,
        label: 'Credentials & Access Keys',
        gradient: 'from-amber-500 to-orange-600',
        bg: 'bg-amber-50',
        border: 'border-amber-200',
        text: 'text-amber-700',
        badge: 'bg-amber-100 text-amber-800',
    },
    apis: {
        icon: Globe,
        label: 'APIs & Integrations',
        gradient: 'from-blue-500 to-indigo-600',
        bg: 'bg-blue-50',
        border: 'border-blue-200',
        text: 'text-blue-700',
        badge: 'bg-blue-100 text-blue-800',
    },
    infrastructure: {
        icon: Server,
        label: 'Infrastructure & Services',
        gradient: 'from-emerald-500 to-teal-600',
        bg: 'bg-emerald-50',
        border: 'border-emerald-200',
        text: 'text-emerald-700',
        badge: 'bg-emerald-100 text-emerald-800',
    },
    databases: {
        icon: Database,
        label: 'Databases & Storage',
        gradient: 'from-violet-500 to-purple-600',
        bg: 'bg-violet-50',
        border: 'border-violet-200',
        text: 'text-violet-700',
        badge: 'bg-violet-100 text-violet-800',
    },
    cloud: {
        icon: Cloud,
        label: 'Cloud Services',
        gradient: 'from-sky-500 to-cyan-600',
        bg: 'bg-sky-50',
        border: 'border-sky-200',
        text: 'text-sky-700',
        badge: 'bg-sky-100 text-sky-800',
    },
    dependencies: {
        icon: Package,
        label: 'Dependencies & Libraries',
        gradient: 'from-rose-500 to-pink-600',
        bg: 'bg-rose-50',
        border: 'border-rose-200',
        text: 'text-rose-700',
        badge: 'bg-rose-100 text-rose-800',
    },
    other: {
        icon: FileKey,
        label: 'Other Prerequisites',
        gradient: 'from-slate-500 to-gray-600',
        bg: 'bg-gray-50',
        border: 'border-gray-200',
        text: 'text-gray-700',
        badge: 'bg-gray-100 text-gray-800',
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
        description: 'Legacy mode (same behavior as AI-First).',
        enabled: true,
    },
    {
        id: 'vibe_coding',
        title: 'Vibe Coding',
        description: 'Upcoming mode.',
        enabled: false,
    },
    {
        id: 'coexistence',
        title: 'Coexistence',
        description: 'Open Status Dashboard with agents available for manual run.',
        enabled: false,
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

    // If AI already returns structured prerequisites
    if (analysisData.prerequisites && Array.isArray(analysisData.prerequisites)) {
        return analysisData.prerequisites.map((p, idx) => ({
            id: idx + 1,
            name: stripHtml(p.name || p.title || `Prerequisite ${idx + 1}`),
            description: stripHtml(p.description || p.details || ''),
            category: p.category || 'other',
            priority: p.priority || 'medium',
            provided: false,
            userNotes: '',
        }));
    }

    // Smart extraction from analysis text
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
        { regex: /(?:aws|azure|gcp|google cloud)[- ]?(?:credentials?|account|subscription|key)/gi, category: 'cloud', label: 'Cloud Service Credentials' },
        { regex: /(?:smtp|email)[- ]?(?:server|credentials?|config)/gi, category: 'infrastructure', label: 'Email/SMTP Configuration' },
        { regex: /(?:ssl|tls)[- ]?(?:certificate|cert)/gi, category: 'credentials', label: 'SSL/TLS Certificate' },
        { regex: /(?:ssh)[- ]?(?:key|access)/gi, category: 'credentials', label: 'SSH Key Access' },
        { regex: /(?:domain|dns)[- ]?(?:name|config|registration)/gi, category: 'infrastructure', label: 'Domain / DNS Configuration' },
        { regex: /(?:docker|container|kubernetes|k8s)/gi, category: 'infrastructure', label: 'Deployment Platform' },
        { regex: /(?:ci[/ ]cd|jenkins|github[- ]?actions|gitlab[- ]?ci|pipeline)/gi, category: 'infrastructure', label: 'CI/CD Pipeline Access' },
        { regex: /(?:redis|memcache|cache[- ]?server)/gi, category: 'databases', label: 'Cache Server (Redis/Memcache)' },
        { regex: /(?:s3|blob[- ]?storage|object[- ]?storage|file[- ]?storage)/gi, category: 'cloud', label: 'Object / File Storage Service' },
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
                provided: false,
                userNotes: '',
            });
        }
    });

    // If nothing was found, add generic ones based on common project needs
    if (items.length === 0) {
        items.push(
            { id: 1, name: 'Environment Configuration', description: 'Set up development, staging, and production environments.', category: 'infrastructure', priority: 'high', provided: false, userNotes: '' },
            { id: 2, name: 'Access Credentials', description: 'Provide necessary credentials for services identified in the BRD.', category: 'credentials', priority: 'high', provided: false, userNotes: '' },
            { id: 3, name: 'Third-Party Integrations', description: 'Confirm access to external APIs and services mentioned in the requirements.', category: 'apis', priority: 'medium', provided: false, userNotes: '' },
        );
    }

    return items;
};

const normalizeGithubRepoPath = (value = '') => {
    const raw = String(value || '').trim();
    if (!raw) return '';

    const asPath = (candidate) => {
        const cleaned = String(candidate || '')
            .trim()
            .replace(/^\/+|\/+$/g, '')
            .replace(/\.git$/i, '');
        const parts = cleaned.split('/').filter(Boolean);
        if (parts.length < 2) return '';
        return `${parts[0]}/${parts[1]}`;
    };

    if (/github\.com/i.test(raw)) {
        try {
            const normalizedUrl = raw.startsWith('http://') || raw.startsWith('https://')
                ? raw
                : `https://${raw}`;
            const url = new URL(normalizedUrl);
            return asPath(url.pathname);
        } catch {
            // Fallback to direct path parsing below.
        }
    }

    return asPath(raw);
};

const repoPathToGitUrl = (repoPath = '') => (
    repoPath ? `https://github.com/${repoPath}.git` : ''
);

const extractRepoSuggestionFromAnalysis = (analysisObj) => {
    if (!analysisObj || typeof analysisObj !== 'object') return null;

    const possibleSources = [
        analysisObj.repoContextMeta,
        analysisObj.repoContext,
        analysisObj.projectMeta?.repoContext,
        analysisObj.projectMeta?.repo_context,
    ].filter(Boolean);

    for (const source of possibleSources) {
        const repoPath = normalizeGithubRepoPath(
            source?.repo || source?.full_name || source?.url || source?.git_repo_url || source?.repository
        );
        if (!repoPath) continue;

        return {
            repo: repoPath,
            branch: String(source?.branch || source?.default_branch || '').trim() || null,
            url: repoPathToGitUrl(repoPath),
            source: String(source?.source || 'analysis'),
        };
    }

    const analysisText = String(analysisObj.analysis || analysisObj.report || '');
    const match = analysisText.match(/Repository:\s*([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)/i);
    if (match?.[1]) {
        const repoPath = normalizeGithubRepoPath(match[1]);
        if (repoPath) {
            return {
                repo: repoPath,
                branch: null,
                url: repoPathToGitUrl(repoPath),
                source: 'analysis',
            };
        }
    }

    return null;
};

const extractRepoSuggestionFromStoredMeta = (storedMeta) => {
    if (!storedMeta || typeof storedMeta !== 'object') return null;
    const repoPath = normalizeGithubRepoPath(
        storedMeta.repo || storedMeta.full_name || storedMeta.url || storedMeta.git_repo_url || storedMeta.repository
    );
    if (!repoPath) return null;
    return {
        repo: repoPath,
        branch: String(storedMeta.branch || storedMeta.default_branch || '').trim() || null,
        url: repoPathToGitUrl(repoPath),
        source: String(storedMeta.source || 'session'),
    };
};

/* ─────────────────────────────────────────────────────────
   PRIORITY BADGE
───────────────────────────────────────────────────────── */
const PriorityBadge = ({ priority }) => {
    const config = {
        high: { bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-200', label: 'High' },
        medium: { bg: 'bg-amber-100', text: 'text-amber-700', border: 'border-amber-200', label: 'Medium' },
        low: { bg: 'bg-green-100', text: 'text-green-700', border: 'border-green-200', label: 'Low' },
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
    const [error, setError] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [submitted, setSubmitted] = useState(false);
    const [processMode, setProcessMode] = useState('ai_first');
    const [projectName, setProjectName] = useState('');
    const [globalGitRepoUrl, setGlobalGitRepoUrl] = useState('');
    const [globalGitToken, setGlobalGitToken] = useState('');
    const [hasSavedGlobalGitToken, setHasSavedGlobalGitToken] = useState(false);
    const [isLoadingGitConfig, setIsLoadingGitConfig] = useState(false);
    const [analysisRepoSuggestion, setAnalysisRepoSuggestion] = useState(null);

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

    useEffect(() => {
        if (selectedProjectKey) {
            const saved = localStorage.getItem(`custom_rules_${selectedProjectKey}`) || '';
            setCustomRules(saved);
        }
    }, [selectedProjectKey]);

    useEffect(() => {
        if (selectedProjectKey) {
            localStorage.setItem(`custom_rules_${selectedProjectKey}`, customRules);
        }
    }, [selectedProjectKey, customRules]);

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
            if (!selectedProjectKey) {
                setGlobalGitRepoUrl('');
                setGlobalGitToken('');
                setHasSavedGlobalGitToken(false);
                return;
            }
            try {
                const token = localStorage.getItem('token');
                if (!token) return;
                setIsLoadingGitConfig(true);

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
    }, [selectedProjectKey, loadStoredProjectRepoSuggestion]);

    // Load analysis data for the selected project
    useEffect(() => {
        const loadAnalysis = async () => {
            setLoading(true);
            setError('');

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

                // Check for previously saved prerequisites for THIS project
                // Use versioned key to bust stale cache with HTML tags
                const PREREQ_CACHE_KEY = `prerequisites_v2_${selectedProjectKey}`;
                const savedPrereqs = sessionStorage.getItem(PREREQ_CACHE_KEY);
                if (savedPrereqs) {
                    try {
                        const parsed = JSON.parse(savedPrereqs);
                        // Validate: reject cache if any description contains HTML tags
                        const hasHtml = parsed.some(p => /<[a-z][\s\S]*>/i.test(p.description || ''));
                        if (!hasHtml && parsed.length > 0) {
                            setPrerequisites(parsed);
                            return;
                        }
                    } catch { /* fall through */ }
                }
                // Also clear old v1 cache
                sessionStorage.removeItem(`prerequisites_${selectedProjectKey}`);

                // Get the project info for matching
                const currentProject = projects?.find(p => p.key === selectedProjectKey);
                const govResultId = currentProject?.governanceResultId;
                const projToken = currentProject?.projectToken || selectedProjectKey;
                const projName = currentProject?.name || projectName;

                // Fetch history to get the latest analysis for THIS specific project
                const res = await fetch(API_ENDPOINTS.HISTORY, {
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
                const projectDoc = docs.find(doc => {
                    if (!doc.analysis_result) return false;
                    try {
                        const analysis = JSON.parse(doc.analysis_result);
                        const meta = analysis.projectMeta || {};
                        const govCtx = analysis.governanceContext || {};

                        const docToken = meta.project_token || govCtx.project_token;
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

                const detectedRepo = extractRepoSuggestionFromAnalysis(analysisObj);
                const storedRepo = loadStoredProjectRepoSuggestion();

                const finalRepoSuggestion = detectedRepo || storedRepo;
                setAnalysisRepoSuggestion(finalRepoSuggestion);
                if (finalRepoSuggestion?.url) {
                    setGlobalGitRepoUrl((prev) => prev.trim() || finalRepoSuggestion.url);
                }

                // Use structured prerequisites from AI if available, otherwise fall back to text extraction
                const extracted = extractPrerequisitesFromAnalysis(analysisObj || projectDoc.analysis_result);
                setPrerequisites(extracted);
            } catch (err) {
                setError('Failed to load analysis data: ' + err.message);
            } finally {
                setLoading(false);
            }
        };

        loadAnalysis();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedProjectKey, navigate, projects, loadStoredProjectRepoSuggestion]);

    // Save prerequisites to session when they change
    useEffect(() => {
        if (prerequisites.length > 0 && selectedProjectKey) {
            sessionStorage.setItem(
                `prerequisites_v2_${selectedProjectKey}`,
                JSON.stringify(prerequisites)
            );
        }
    }, [prerequisites, selectedProjectKey]);

    const toggleProvided = useCallback((id) => {
        setPrerequisites(prev =>
            prev.map(p => p.id === id ? { ...p, provided: !p.provided } : p)
        );
    }, []);

    const updateNotes = useCallback((id, notes) => {
        setPrerequisites(prev =>
            prev.map(p => p.id === id ? { ...p, userNotes: notes, provided: notes.trim().length > 0 ? true : p.provided } : p)
        );
    }, []);

    // Group by category
    const grouped = useMemo(() => {
        const groups = {};
        prerequisites.forEach(p => {
            if (!groups[p.category]) groups[p.category] = [];
            groups[p.category].push(p);
        });
        return groups;
    }, [prerequisites]);

    const totalItems = prerequisites.length;
    const providedCount = prerequisites.filter(p => p.provided).length;
    const progress = totalItems > 0 ? Math.round((providedCount / totalItems) * 100) : 0;
    const allProvided = processMode === 'developer_only' ? true : (totalItems > 0 && providedCount === totalItems);
    const shouldShowRepoSuggestion = Boolean(
        analysisRepoSuggestion &&
        !isLoadingGitConfig &&
        processMode !== 'developer_only'
    );
    const isGlobalGitConfigValid = processMode === 'developer_only' || Boolean(
        globalGitRepoUrl.trim() && (hasSavedGlobalGitToken || globalGitToken.trim())
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
                throw new Error('No project selected.');
            }

            if (processMode !== 'developer_only') {
                const repo = globalGitRepoUrl.trim();
                const pat = globalGitToken.trim();
                if (!repo) {
                    throw new Error('Git repository URL is required.');
                }
                if (!hasSavedGlobalGitToken && !pat) {
                    throw new Error('Global PAT is required.');
                }

                // Save global Git config from prerequisites so all agents reuse it.
                const agentsUrl = new URL(API_ENDPOINTS.AGENTS);
                agentsUrl.searchParams.set('project_token', selectedProjectKey);
                const agentsRes = await fetch(agentsUrl.toString(), {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (!agentsRes.ok) {
                    throw new Error('Failed to load agents for saving global Git config.');
                }
                const agentsData = await agentsRes.json().catch(() => ({}));
                const agentList = Array.isArray(agentsData?.agents) ? agentsData.agents : [];
                const targetAgent =
                    agentList.find((a) => a?.id !== 'agent_03' && a?.id !== 'agent_04') || agentList[0];
                if (!targetAgent?.id) {
                    throw new Error('No agent available to save global Git config.');
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
                    throw new Error(errData?.detail || 'Failed to save  Git config.');
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
                items: prerequisites.map(p => ({
                    name: p.name,
                    description: p.description,
                    category: p.category,
                    priority: p.priority,
                    provided: p.provided,
                    userNotes: p.userNotes,
                })),
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

            // Mark prerequisites as completed on the backend
            await fetch(API_ENDPOINTS.GOVERNANCE_PREREQUISITES_COMPLETE(selectedProjectKey), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
            });

            // Refresh roadmap to reflect that prerequisites are done
            if (fetchRoadmapData && selectedProjectKey) {
                await fetchRoadmapData(selectedProjectKey);
            }

            // Save selected execution mode
            saveProcessModeForProject(selectedProjectKey, processMode);

            if (processMode === 'developer_only') {
                // Redirect immediately without showing the checkmark screen
                window.location.href = 'vscode:extension/bourntec-Solutions.n-mod-vscode-assistant';
                return; // Stop execution here so it doesn't clear the submitting state right away
            } else {
                setSubmitted(true);
                // After a brief success animation, redirect to Task Creation
                setTimeout(() => {
                    navigate('/task-creation');
                }, 1500);
            }
        } catch (err) {
            setError('Failed to save prerequisites: ' + err.message);
        } finally {
            if (processMode !== 'developer_only') {
                setSubmitting(false);
            }
        }
    };

    /* ── Loading State ── */
    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
                <div className="flex flex-col items-center gap-5">
                    <div className="relative">
                        <div className="w-14 h-14 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
                        <div className="absolute inset-0 w-14 h-14 border-4 border-transparent border-b-indigo-400 rounded-full animate-spin" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }} />
                    </div>
                    <div className="text-center">
                        <p className="text-gray-600 font-semibold text-sm tracking-wide">Analyzing prerequisites…</p>
                        <p className="text-gray-400 text-xs mt-1">Extracting requirements from AI analysis</p>
                    </div>
                </div>
            </div>
        );
    }

    /* ── Submitted Success State ── */
    if (submitted) {
        return (
            <div className="h-full overflow-y-auto bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
                <div className="max-w-2xl mx-auto px-4 py-16">
                    <div className="bg-white/90 backdrop-blur-xl rounded-2xl shadow-lg border border-white/60 p-10 text-center relative overflow-hidden">
                        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-emerald-500 via-teal-500 to-green-500 rounded-t-2xl" />

                        <div className="w-20 h-20 mx-auto mb-6 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-full flex items-center justify-center shadow-lg shadow-emerald-200">
                            <CheckCircle2 className="w-10 h-10 text-white" />
                        </div>

                        <h2 className="text-2xl font-extrabold text-gray-900 mb-2 tracking-tight">Prerequisites Acknowledged</h2>
                        <p className="text-gray-500 text-sm mb-6 leading-relaxed max-w-md mx-auto">
                            {providedCount} of {totalItems} prerequisite items have been confirmed for <strong>{projectName || 'this project'}</strong>.
                        </p>

                        <div className="flex items-center justify-center gap-2 text-sm text-gray-400">
                            <div className="w-4 h-4 border-2 border-gray-300 border-t-emerald-500 rounded-full animate-spin" />
                            {processMode === 'developer_only' ? 'Redirecting to VS Code Extension…' : 'Redirecting to Task Creation…'}
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    /* ── Main View ── */
    return (
        <div className="h-full overflow-y-auto bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
            <div className="px-3 sm:px-4 lg:px-6 py-4 lg:py-6 max-w-[1200px] mx-auto">

                {/* Back Link */}
                <button
                    onClick={() => navigate('/dashboard')}
                    className="inline-flex items-center gap-1.5 text-sm font-semibold text-gray-500 hover:text-gray-800 mb-5 transition-colors group"
                >
                    <ChevronLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" /> Back to Dashboard
                </button>

                {/* ── HERO HEADER ── */}
                <div className="relative rounded-2xl overflow-hidden bg-gradient-to-br from-slate-700 via-gray-800 to-slate-900 text-white p-6 sm:p-8 shadow-xl mb-6">
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

                {/* ── PROGRESS BAR (mobile) ── */}
                <div className="sm:hidden mb-4">
                    <div className="flex items-center justify-between text-xs mb-1.5">
                        <span className="font-bold text-blue-600">{providedCount} of {totalItems} confirmed</span>
                        <span className="text-gray-400 font-semibold">{progress}%</span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                        <div
                            className="bg-gradient-to-r from-amber-400 to-amber-500 h-full rounded-full transition-all duration-500 ease-out"
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                </div>

                {/* ── EXECUTION MODE (Grid View) ── */}
                <div className="bg-white/90 backdrop-blur-xl rounded-2xl shadow-sm border border-gray-100/80 p-6 mb-6">
                    <h3 className="text-base font-bold text-gray-900 mb-1">Choose Execution Mode</h3>
                    <p className="text-sm text-gray-500 mb-4">Select how this project should run in Status Dashboard.</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {PROCESS_MODE_OPTIONS.map(option => (
                            <button
                                key={option.id}
                                type="button"
                                disabled={!option.enabled}
                                onClick={() => setProcessMode(option.id)}
                                className={`text-left rounded-xl border p-4 transition-all ${processMode === option.id && option.enabled
                                    ? 'border-indigo-500 bg-indigo-50 shadow-sm ring-1 ring-indigo-500'
                                    : option.enabled
                                        ? 'border-gray-200 bg-white hover:bg-gray-50 hover:border-indigo-300'
                                        : 'border-gray-200 bg-gray-50 text-gray-400 cursor-not-allowed'
                                    }`}
                            >
                                <div className="flex items-center justify-between gap-2 mb-1.5">
                                    <p className={`text-sm font-bold ${option.enabled ? (processMode === option.id ? 'text-indigo-900' : 'text-gray-900') : 'text-gray-500'}`}>
                                        {option.title}
                                    </p>
                                    {!option.enabled && (
                                        <span className="text-[9px] font-bold uppercase tracking-wide text-gray-500 bg-gray-200 px-2 py-0.5 rounded-full">
                                            Disabled
                                        </span>
                                    )}
                                    {processMode === option.id && option.enabled && (
                                        <CheckCircle2 className="w-4 h-4 text-indigo-600" />
                                    )}
                                </div>
                                <p className={`text-xs ${processMode === option.id && option.enabled ? 'text-indigo-700' : 'text-gray-500'}`}>
                                    {option.description}
                                </p>
                            </button>
                        ))}
                    </div>
                </div>

                {/* ── ERROR ── */}
                {error && (
                    <div className="rounded-xl bg-red-50/80 backdrop-blur-sm p-4 border border-red-200/60 text-red-700 mb-5 flex items-start gap-3 shadow-sm">
                        <div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center flex-shrink-0">
                            <AlertCircle className="w-4 h-4 text-red-500" />
                        </div>
                        <div className="text-sm font-medium pt-1">{error}</div>
                    </div>
                )}

                {/* ── INFO TIP ── */}
                <div className="bg-blue-50/80 rounded-xl border border-blue-200/60 p-4 mb-6 flex items-start gap-3">
                    <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
                    <div>
                        <p className="text-sm font-semibold text-blue-900 mb-0.5">How this works</p>
                        <p className="text-xs text-blue-700 leading-relaxed">
                            Our AI has analyzed your BRD and identified the services, credentials, and infrastructure
                            you'll need. Review each item and mark it as "Provided" once you've arranged access.
                            Add notes for your team as needed.
                        </p>
                    </div>
                </div>

                {/* ── PREREQUISITES SECTION ── */}
                {processMode === 'developer_only' ? (
                    <div className="bg-white/90 backdrop-blur-xl rounded-2xl shadow-sm border border-gray-100/80 p-8 text-center mb-8 border-dashed border-blue-200">
                        <div className="w-16 h-16 mx-auto mb-4 bg-blue-50 rounded-full flex items-center justify-center">
                            <ArrowRight className="w-8 h-8 text-blue-500" />
                        </div>
                        <h3 className="text-lg font-bold text-gray-900 mb-2">Direct Developer Workflow</h3>
                        <p className="text-sm text-gray-600 max-w-lg mx-auto leading-relaxed">
                            Prerequisite classification is bypassed for <strong>Developer Only</strong> mode.
                            You will be redirected to VS Code.
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
                                <div key={category} className="bg-white/90 backdrop-blur-xl rounded-2xl shadow-sm border border-gray-100/80 overflow-hidden">
                                    {/* Category Header */}
                                    <div className={`flex items-center justify-between px-5 py-3.5 ${config.bg} border-b ${config.border}`}>
                                        <div className="flex items-center gap-3">
                                            <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${config.gradient} flex items-center justify-center shadow-sm`}>
                                                <CategoryIcon className="w-4 h-4 text-white" />
                                            </div>
                                            <div>
                                                <h3 className={`text-sm font-bold ${config.text}`}>{config.label}</h3>
                                                <p className="text-[11px] text-gray-500">{catProvided}/{items.length} confirmed</p>
                                            </div>
                                        </div>
                                        <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full ${config.badge}`}>
                                            {items.length} {items.length === 1 ? 'item' : 'items'}
                                        </span>
                                    </div>

                                    {/* Items */}
                                    <div className="divide-y divide-gray-100">
                                        {items.map(item => (
                                            <div
                                                key={item.id}
                                                className={`px-5 py-4 flex items-start gap-4 transition-all duration-200 ${item.provided ? 'bg-emerald-50/40' : 'hover:bg-gray-50/50'
                                                    }`}
                                            >
                                                {/* Checkbox */}
                                                <button
                                                    onClick={() => toggleProvided(item.id)}
                                                    className="flex-shrink-0 mt-0.5 transition-transform active:scale-90"
                                                    title={item.provided ? 'Mark as not provided' : 'Mark as provided'}
                                                >
                                                    {item.provided ? (
                                                        <CheckCircle2 className="w-6 h-6 text-emerald-500 drop-shadow-sm" />
                                                    ) : (
                                                        <Circle className="w-6 h-6 text-gray-300 hover:text-gray-400" />
                                                    )}
                                                </button>

                                                {/* Content */}
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                                                        <span className={`text-sm font-semibold ${item.provided ? 'text-gray-500' : 'text-gray-800'}`}>
                                                            {item.name}
                                                        </span>
                                                        <PriorityBadge priority={item.priority} />
                                                    </div>
                                                    <p className="text-xs text-gray-500 leading-relaxed mb-2.5 max-w-2xl">
                                                        {item.description}
                                                    </p>

                                                    {/* Notes field */}
                                                    <textarea
                                                        value={item.userNotes}
                                                        onChange={(e) => updateNotes(item.id, e.target.value)}
                                                        placeholder="Add notes (optional) — e.g., credentials location, contact person…"
                                                        rows={1}
                                                        className="w-full text-xs text-gray-600 bg-gray-50/80 border border-gray-200 rounded-lg px-3 py-2 placeholder:text-gray-300 focus:ring-2 focus:ring-blue-100 focus:border-blue-300 transition-all resize-none"
                                                    />
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
                {processMode !== 'developer_only' && (
                    <div className="bg-white/90 backdrop-blur-xl rounded-2xl shadow-sm border border-gray-100/80 p-6 mb-6 space-y-4">
                        <div className="flex items-center gap-2 mb-1">
                            <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center">
                                <Sparkles className="w-4 h-4 text-indigo-600" />
                            </div>
                            <h3 className="text-base font-bold text-gray-900">A.I. Custom Rules</h3>
                        </div>
                        <p className="text-sm text-gray-500">
                            Define specific coding standards, architectural patterns, or task constraints. The AI will follow these instructions when generating the project plan and tasks.
                        </p>
                        <textarea
                            value={customRules}
                            onChange={(e) => setCustomRules(e.target.value)}
                            placeholder="e.g. Use functional components for React, follow SOLID principles, all API tasks must include error handling documentation..."
                            className="w-full min-h-[120px] p-4 text-sm text-gray-900 bg-slate-50 border border-gray-200 rounded-xl focus:ring-4 focus:ring-indigo-100 focus:border-indigo-400 transition-all outline-none resize-y"
                        />
                        <div className="flex items-center gap-2 text-[11px] text-indigo-500 font-medium bg-indigo-50/50 px-3 py-2 rounded-lg italic">
                            <AlertCircle className="w-3.5 h-3.5" />
                            Rules are saved automatically for this project.
                        </div>
                    </div>
                )}

                {/* ── SUMMARY + SUBMIT ── */}
                <div className="bg-white/90 backdrop-blur-xl rounded-2xl shadow-lg border border-gray-100/80 p-6 mb-6">
                    {processMode !== 'developer_only' && (
                        <div className="mb-6 pb-6 border-b border-gray-100">
                            <h3 className="text-base font-bold text-gray-900 mb-1">Git Configuration</h3>
                            <p className="text-sm text-gray-500 mb-4">
                                Provide one global repository and PAT here. All agents in this project will use these credentials.
                            </p>
                            {shouldShowRepoSuggestion && (
                                <div className="mb-4 rounded-xl border border-indigo-200 bg-indigo-50/80 p-4">
                                    <p className="text-sm font-semibold text-indigo-900">Repository detected from analysis</p>
                                    <p className="text-xs text-indigo-700 mt-1">
                                        Using <span className="font-semibold">{analysisRepoSuggestion.repo}</span>
                                        {analysisRepoSuggestion.branch ? ` (${analysisRepoSuggestion.branch})` : ''} from BRD section for this project.
                                        You can change it below if needed.
                                    </p>
                                </div>
                            )}
                            <div className="grid grid-cols-1 gap-4">
                                <div>
                                    <label className="block text-[11px] font-bold text-gray-600 mb-2 uppercase tracking-widest">
                                        Git Repository URL <span className="text-red-500">*</span>
                                    </label>
                                    <input
                                        type="text"
                                        value={globalGitRepoUrl}
                                        onChange={(e) => setGlobalGitRepoUrl(e.target.value)}
                                        placeholder="https://github.com/org/repo.git"
                                        className="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:ring-4 focus:ring-blue-100 focus:border-blue-400 text-sm bg-white text-gray-900 transition-all duration-200"
                                    />
                                </div>
                                <div>
                                    <label className="block text-[11px] font-bold text-gray-600 mb-2 uppercase tracking-widest">
                                        Personal Access Token {!hasSavedGlobalGitToken && <span className="text-red-500">*</span>}
                                    </label>
                                    <input
                                        type="password"
                                        value={globalGitToken}
                                        onChange={(e) => setGlobalGitToken(e.target.value)}
                                        placeholder={hasSavedGlobalGitToken ? 'Leave blank to keep existing PAT' : 'ghp_...'}
                                        className="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:ring-4 focus:ring-blue-100 focus:border-blue-400 text-sm bg-white text-gray-900 transition-all duration-200"
                                    />
                                    <p className="text-xs text-gray-500 mt-2">
                                        {hasSavedGlobalGitToken
                                            ? 'PAT already saved for this project. Enter a new one only if you want to replace it.'
                                            : 'PAT is required the first time so agents can clone/push to the global repository.'}
                                    </p>
                                </div>
                                {isLoadingGitConfig && (
                                    <p className="text-xs text-gray-500">Loading saved Git config...</p>
                                )}
                            </div>
                        </div>
                    )}

                    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                        <div>
                            <h3 className="text-base font-bold text-gray-900 mb-1">Ready to proceed?</h3>
                            <p className="text-sm text-gray-500">
                                {processMode === 'developer_only'
                                    ? '🚀 You will be redirected to VS Code to use N-Mod Extension.'
                                    : allProvided
                                        ? '✅ All prerequisites confirmed. You can proceed to task creation.'
                                        : `${totalItems - providedCount} item${totalItems - providedCount !== 1 ? 's' : ''} still pending. You can still proceed, but ensure all items are addressed before agent execution.`
                                }
                            </p>
                        </div>

                        <button
                            onClick={handleSubmit}
                            disabled={submitting || isLoadingGitConfig || !isGlobalGitConfigValid}
                            className={`inline-flex items-center gap-2 py-3 px-7 text-sm font-bold rounded-xl text-white transition-all shadow-lg active:scale-[0.97] flex-shrink-0 ${allProvided
                                ? 'bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 shadow-emerald-200/50'
                                : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-blue-200/50'
                                } disabled:from-gray-300 disabled:to-gray-400 disabled:cursor-not-allowed disabled:shadow-none`}
                        >
                            {submitting ? (
                                <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</>
                            ) : (
                                <>{(allProvided || processMode === 'developer_only') ? <CheckCircle2 className="w-4 h-4" /> : <ArrowRight className="w-4 h-4" />}
                                    {processMode === 'developer_only' ? 'Redirect to VS Code' : (allProvided ? 'Confirm & Proceed' : 'Proceed Anyway')}</>
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default PrerequisiteClassification;
