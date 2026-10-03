import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
    X,
    Folder,
    FolderOpen,
    FileText,
    ChevronRight,
    ChevronDown,
    RefreshCw,
    Search,
    Copy,
    Check,
    Download,
    Maximize2,
    Minimize2,
    Code2,
    Cpu,
    GitBranch,
    Clock,
    Sparkles,
    CheckCircle2,
    Radio,
    Terminal,
    Layers,
    FileCode,
    Activity,
    SlidersHorizontal,
    PanelLeft,
    PanelLeftClose,
    Eye,
    EyeOff,
    WrapText,
    Lock,
} from 'lucide-react';
import { API_ENDPOINTS } from '../config';

// ── File Icon & Color Mapper ───────────────────────────────────────────────
function getFileIcon(filename) {
    const lower = filename.toLowerCase();

    // Check .env files (.env, .env.example, .env.local, .env.production, etc.)
    if (lower === '.env' || lower.startsWith('.env.') || lower.endsWith('.env')) {
        return { icon: '🔒', color: '#10b981', label: 'ENV' };
    }
    if (lower === '.gitignore' || lower === '.dockerignore') {
        return { icon: '👁️', color: '#f97316', label: 'GitIgnore' };
    }
    if (lower === 'dockerfile' || lower.endsWith('.dockerfile')) {
        return { icon: '🐳', color: '#0db7ed', label: 'Docker' };
    }

    const ext = lower.split('.').pop();
    switch (ext) {
        case 'py':
            return { icon: '🐍', color: '#3572A5', label: 'Python' };
        case 'js':
            return { icon: '🟨', color: '#f1e05a', label: 'JavaScript' };
        case 'jsx':
            return { icon: '⚛️', color: '#61dafb', label: 'React JSX' };
        case 'ts':
            return { icon: '🔷', color: '#3178c6', label: 'TypeScript' };
        case 'tsx':
            return { icon: '⚛️', color: '#3178c6', label: 'React TSX' };
        case 'json':
            return { icon: '📋', color: '#cbcb41', label: 'JSON' };
        case 'css':
            return { icon: '🎨', color: '#563d7c', label: 'CSS' };
        case 'html':
            return { icon: '🌐', color: '#e34c26', label: 'HTML' };
        case 'md':
            return { icon: '📝', color: '#42a5f5', label: 'Markdown' };
        case 'sql':
            return { icon: '🗄️', color: '#00758f', label: 'SQL' };
        case 'sh':
            return { icon: '⚡', color: '#89e051', label: 'Shell' };
        case 'yml':
        case 'yaml':
            return { icon: '⚙️', color: '#cb171e', label: 'YAML' };
        case 'toml':
        case 'ini':
            return { icon: '🔧', color: '#9e6a03', label: 'Config' };
        default:
            return { icon: '📄', color: '#858585', label: ext.toUpperCase() || 'Text' };
    }
}

// ── Agent Lane Colors ───────────────────────────────────────────────────────
function getAgentBadge(agentName = '', lane = '') {
    const lower = (agentName + ' ' + lane).toLowerCase();
    if (lower.includes('backend') || lower.includes('dev_agent') || lower.includes('agent_01')) {
        return {
            name: agentName || 'BackendAgent',
            bg: 'bg-blue-900/60',
            text: 'text-blue-300',
            border: 'border-blue-700/60',
            dot: 'bg-blue-400',
        };
    }
    if (lower.includes('frontend') || lower.includes('ui_agent') || lower.includes('agent_02')) {
        return {
            name: agentName || 'FrontendAgent',
            bg: 'bg-purple-900/60',
            text: 'text-purple-300',
            border: 'border-purple-700/60',
            dot: 'bg-purple-400',
        };
    }
    if (lower.includes('qa') || lower.includes('test')) {
        return {
            name: agentName || 'QAAgent',
            bg: 'bg-emerald-900/60',
            text: 'text-emerald-300',
            border: 'border-emerald-700/60',
            dot: 'bg-emerald-400',
        };
    }
    if (lower.includes('contract') || lower.includes('master')) {
        return {
            name: agentName || 'Coordinator',
            bg: 'bg-amber-900/60',
            text: 'text-amber-300',
            border: 'border-amber-700/60',
            dot: 'bg-amber-400',
        };
    }
    return {
        name: agentName || 'System',
        bg: 'bg-gray-800/80',
        text: 'text-gray-300',
        border: 'border-gray-700',
        dot: 'bg-gray-400',
    };
}

// ── Minimal Syntax Highlighter for Live Code View ──────────────────────────
function highlightLine(line, lang = '', maskSecrets = false) {
    if (!line) return <span>&nbsp;</span>;

    const trimmed = line.trim();

    // Single-line comment
    if (trimmed.startsWith('#') || trimmed.startsWith('//')) {
        return <span className="text-gray-500 italic select-none">{line}</span>;
    }

    const isEnv = lang === 'env' || lang === 'properties' || lang === 'dotenv';

    // Dedicated high-fidelity .env parsing
    if (isEnv) {
        const eqIdx = line.indexOf('=');
        if (eqIdx !== -1) {
            const rawKey = line.substring(0, eqIdx);
            const rawVal = line.substring(eqIdx + 1);

            // Determine if key is sensitive or if user chose to mask secrets
            const isSensitive = /secret|key|token|password|auth|pwd|cred|salt|private/i.test(rawKey);
            const shouldMask = maskSecrets && isSensitive;

            const valTrimmed = rawVal.trim();
            let valColor = 'text-[#ce9178]'; // default string color (orange/amber)
            if (valTrimmed.toLowerCase() === 'true' || valTrimmed.toLowerCase() === 'false') {
                valColor = 'text-[#4fc1ff] font-semibold';
            } else if (/^\d+(\.\d+)?$/.test(valTrimmed)) {
                valColor = 'text-[#b5cea8]';
            } else if (valTrimmed.startsWith('http://') || valTrimmed.startsWith('https://') || valTrimmed.startsWith('postgres://') || valTrimmed.startsWith('sqlite:')) {
                valColor = 'text-[#9cdcfe] underline decoration-gray-600';
            }

            return (
                <span>
                    <span className="text-[#4ec9b0] font-semibold">{rawKey}</span>
                    <span className="text-gray-400 font-bold mx-0.5">=</span>
                    {shouldMask ? (
                        <span className="text-amber-400/90 font-mono tracking-widest bg-amber-950/40 px-1.5 py-0.5 rounded text-[11px] select-none border border-amber-900/50">
                            ••••••••••••
                        </span>
                    ) : (
                        <span className={valColor}>{rawVal}</span>
                    )}
                </span>
            );
        }
    }

    // Tokenizer matching strings, keywords, numbers for code
    const tokens = [];
    const regex = /(["'`].*?["'`])|(\b(?:import|export|from|def|class|return|if|else|elif|for|while|try|except|finally|async|await|const|let|var|function|type|interface|extends|implements|as|with|in|is|not|and|or|true|false|True|False|null|None)\b)|(\b\d+(\.\d+)?\b)|(\b[A-Za-z0-9_]+(?=\())\b/g;

    let lastIdx = 0;
    let match;

    while ((match = regex.exec(line)) !== null) {
        if (match.index > lastIdx) {
            tokens.push({ text: line.substring(lastIdx, match.index), type: 'plain' });
        }
        if (match[1]) {
            tokens.push({ text: match[1], type: 'string' });
        } else if (match[2]) {
            tokens.push({ text: match[2], type: 'keyword' });
        } else if (match[3]) {
            tokens.push({ text: match[3], type: 'number' });
        } else if (match[5]) {
            tokens.push({ text: match[5], type: 'function' });
        }
        lastIdx = regex.lastIndex;
    }

    if (lastIdx < line.length) {
        tokens.push({ text: line.substring(lastIdx), type: 'plain' });
    }

    return (
        <span>
            {tokens.map((t, idx) => {
                if (t.type === 'string') return <span key={idx} className="text-[#ce9178]">{t.text}</span>;
                if (t.type === 'keyword') return <span key={idx} className="text-[#569cd6] font-semibold">{t.text}</span>;
                if (t.type === 'number') return <span key={idx} className="text-[#b5cea8]">{t.text}</span>;
                if (t.type === 'function') return <span key={idx} className="text-[#dcdcaa]">{t.text}</span>;
                return <span key={idx} className="text-[#d4d4d4]">{t.text}</span>;
            })}
        </span>
    );
}

// ── Build Hierarchical File Tree from Flat List ────────────────────────────
function buildFileTree(files) {
    const root = { name: 'workspace', isDir: true, children: {}, path: '' };

    for (const f of files) {
        const parts = f.path.split('/');
        let current = root;

        for (let i = 0; i < parts.length; i++) {
            const part = parts[i];
            const isLast = i === parts.length - 1;

            if (isLast) {
                current.children[part] = {
                    ...f,
                    isDir: false,
                    displayName: part,
                };
            } else {
                if (!current.children[part]) {
                    const subPath = parts.slice(0, i + 1).join('/');
                    current.children[part] = {
                        name: part,
                        displayName: part,
                        isDir: true,
                        path: subPath,
                        children: {},
                    };
                }
                current = current.children[part];
            }
        }
    }
    return root;
}

export default function VSCodeWorkspaceViewer({ isOpen, onClose, projectToken = 'default_project' }) {
    const [files, setFiles] = useState([]);
    const [activeAgents, setActiveAgents] = useState([]);
    const [loadingFiles, setLoadingFiles] = useState(false);
    const [expandedFolders, setExpandedFolders] = useState({});
    const [openTabs, setOpenTabs] = useState([]);
    const [activeTabPath, setActiveTabPath] = useState(null);
    const [fileContentMap, setFileContentMap] = useState({});
    const [loadingContent, setLoadingContent] = useState(false);
    const [copied, setCopied] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [autoPoll, setAutoPoll] = useState(true);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [lastSyncTime, setLastSyncTime] = useState(null);
    const [activeSidebarTab, setActiveSidebarTab] = useState('explorer'); // 'explorer' | 'agents'

    // Responsive and viewing control states
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [wordWrap, setWordWrap] = useState(true);
    const [maskSecrets, setMaskSecrets] = useState(false);
    const [isMobile, setIsMobile] = useState(false);

    const pollTimerRef = useRef(null);

    // Responsive screen width tracker
    useEffect(() => {
        const checkMobile = () => {
            const mobile = window.innerWidth < 768;
            setIsMobile(mobile);
            // On mobile start with sidebar closed to give full space to code
            if (mobile) {
                setSidebarOpen(false);
            } else {
                setSidebarOpen(true);
            }
        };
        checkMobile();
        window.addEventListener('resize', checkMobile);
        return () => window.removeEventListener('resize', checkMobile);
    }, []);

    // Handle Escape key to close modal
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === 'Escape') {
                onClose();
            }
        };
        if (isOpen) {
            window.addEventListener('keydown', handleKeyDown);
        }
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isOpen, onClose]);

    // ── Fetch File Tree & Active Agents ────────────────────────────────────
    const fetchWorkspaceFiles = useCallback(async (isInitial = false) => {
        if (isInitial) setLoadingFiles(true);
        const token = localStorage.getItem('token');
        try {
            const url = API_ENDPOINTS.AGENT_WORKSPACE_FILES(projectToken);
            const res = await fetch(url, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (res.ok) {
                const data = await res.json();
                const fetchedFiles = data.files || [];
                setFiles(fetchedFiles);
                setActiveAgents(data.active_agents || []);
                setLastSyncTime(new Date());

                // Auto-expand top level folders initially
                if (isInitial && fetchedFiles.length > 0) {
                    const initialExpanded = { '': true };
                    fetchedFiles.forEach(f => {
                        const topDir = f.path.split('/')[0];
                        if (f.path.includes('/')) {
                            initialExpanded[topDir] = true;
                        }
                    });
                    setExpandedFolders(initialExpanded);

                    // Auto-open first modified or important file
                    const primeFile = fetchedFiles.find(f => f.is_recent) || fetchedFiles[0];
                    if (primeFile && openTabs.length === 0) {
                        handleOpenFile(primeFile.path, false);
                    }
                }
            }
        } catch (err) {
            console.error('Error fetching workspace files:', err);
        } finally {
            if (isInitial) setLoadingFiles(false);
        }
    }, [projectToken]);

    // ── Fetch Specific File Content ────────────────────────────────────────
    const fetchFileContent = useCallback(async (filePath) => {
        if (!filePath) return;
        setLoadingContent(true);
        const token = localStorage.getItem('token');
        try {
            const url = API_ENDPOINTS.AGENT_WORKSPACE_FILE_CONTENT(projectToken, filePath);
            const res = await fetch(url, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (res.ok) {
                const data = await res.json();
                setFileContentMap(prev => ({
                    ...prev,
                    [filePath]: {
                        content: data.content || '',
                        language: data.language || 'text',
                        size: data.size || 0,
                        modified_at: data.modified_at,
                    },
                }));
            } else {
                setFileContentMap(prev => ({
                    ...prev,
                    [filePath]: {
                        content: `// Error loading file content: ${res.statusText}`,
                        language: 'text',
                    },
                }));
            }
        } catch (err) {
            setFileContentMap(prev => ({
                ...prev,
                [filePath]: {
                    content: `// Error fetching file: ${err.message}`,
                    language: 'text',
                },
            }));
        } finally {
            setLoadingContent(false);
        }
    }, [projectToken]);

    // ── Open a File in Tabs ────────────────────────────────────────────────
    const handleOpenFile = useCallback((filePath, closeDrawerOnMobile = true) => {
        if (!openTabs.includes(filePath)) {
            setOpenTabs(prev => [...prev, filePath]);
        }
        setActiveTabPath(filePath);
        fetchFileContent(filePath);

        // On mobile, automatically close drawer after picking a file so code is immediately visible
        if (closeDrawerOnMobile && window.innerWidth < 768) {
            setSidebarOpen(false);
        }
    }, [openTabs, fetchFileContent]);

    // ── Close Tab ─────────────────────────────────────────────────────────
    const handleCloseTab = useCallback((filePath, e) => {
        e?.stopPropagation();
        setOpenTabs(prev => {
            const filtered = prev.filter(p => p !== filePath);
            if (activeTabPath === filePath) {
                const nextActive = filtered[filtered.length - 1] || null;
                setActiveTabPath(nextActive);
                if (nextActive && !fileContentMap[nextActive]) {
                    fetchFileContent(nextActive);
                }
            }
            return filtered;
        });
    }, [activeTabPath, fileContentMap, fetchFileContent]);

    // ── Toggle Folder Expansion ───────────────────────────────────────────
    const toggleFolder = useCallback((folderPath) => {
        setExpandedFolders(prev => ({
            ...prev,
            [folderPath]: !prev[folderPath],
        }));
    }, []);

    // ── Initial load & live polling ───────────────────────────────────────
    useEffect(() => {
        if (!isOpen) return;
        fetchWorkspaceFiles(true);

        if (autoPoll) {
            pollTimerRef.current = setInterval(() => {
                fetchWorkspaceFiles(false);
                // Also refresh currently active file content so live edits appear immediately
                if (activeTabPath) {
                    fetchFileContent(activeTabPath);
                }
            }, 2500);
        }

        return () => {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
        };
    }, [isOpen, autoPoll, activeTabPath, fetchWorkspaceFiles, fetchFileContent]);

    // ── Copy Code ──────────────────────────────────────────────────────────
    const handleCopy = () => {
        const currentData = activeTabPath ? fileContentMap[activeTabPath] : null;
        if (currentData?.content) {
            navigator.clipboard.writeText(currentData.content);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    // ── Download File ──────────────────────────────────────────────────────
    const handleDownload = () => {
        const currentData = activeTabPath ? fileContentMap[activeTabPath] : null;
        if (!currentData || !activeTabPath) return;
        const blob = new Blob([currentData.content], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = activeTabPath.split('/').pop() || 'file';
        a.click();
        URL.revokeObjectURL(url);
    };

    // ── Filter Files ───────────────────────────────────────────────────────
    const filteredFiles = useMemo(() => {
        if (!searchQuery.trim()) return files;
        const q = searchQuery.toLowerCase();
        return files.filter(f =>
            f.path.toLowerCase().includes(q) ||
            f.attributed_agent?.toLowerCase().includes(q) ||
            f.lane?.toLowerCase().includes(q)
        );
    }, [files, searchQuery]);

    const fileTree = useMemo(() => buildFileTree(filteredFiles), [filteredFiles]);

    // Current active file details
    const activeFileMeta = useMemo(() => {
        return files.find(f => f.path === activeTabPath);
    }, [files, activeTabPath]);

    const activeContentData = activeTabPath ? fileContentMap[activeTabPath] : null;
    const contentLines = useMemo(() => {
        if (!activeContentData?.content) return [];
        return activeContentData.content.split('\n');
    }, [activeContentData]);

    const isEnvFile = useMemo(() => {
        if (!activeTabPath) return false;
        const lower = activeTabPath.toLowerCase();
        return lower.includes('.env') || activeContentData?.language === 'env';
    }, [activeTabPath, activeContentData]);

    if (!isOpen) return null;

    // Handle Activity Bar clicks (VS Code style toggle)
    const handleActivityTabClick = (tab) => {
        if (activeSidebarTab === tab && sidebarOpen) {
            setSidebarOpen(false);
        } else {
            setActiveSidebarTab(tab);
            setSidebarOpen(true);
        }
    };

    // ── Render Tree Node ───────────────────────────────────────────────────
    const renderNode = (node, depth = 0) => {
        if (!node) return null;

        if (node.isDir) {
            const isRoot = node.name === 'workspace';
            const isExpanded = isRoot || !!expandedFolders[node.path];

            return (
                <div key={node.path || 'root'} className="select-none">
                    {!isRoot && (
                        <div
                            onClick={() => toggleFolder(node.path)}
                            style={{ paddingLeft: `${depth * 12 + 6}px` }}
                            className="flex items-center gap-1.5 py-1 px-2 hover:bg-[#2a2d2e] cursor-pointer text-gray-300 hover:text-white transition-colors group text-xs font-mono"
                        >
                            {isExpanded ? (
                                <ChevronDown className="w-3.5 h-3.5 text-gray-400 group-hover:text-white shrink-0" />
                            ) : (
                                <ChevronRight className="w-3.5 h-3.5 text-gray-400 group-hover:text-white shrink-0" />
                            )}
                            {isExpanded ? (
                                <FolderOpen className="w-4 h-4 text-[#dcb67a] shrink-0" />
                            ) : (
                                <Folder className="w-4 h-4 text-[#dcb67a] shrink-0" />
                            )}
                            <span className="truncate font-semibold">{node.displayName}</span>
                        </div>
                    )}
                    {isExpanded && (
                        <div>
                            {Object.values(node.children)
                                .sort((a, b) => {
                                    if (a.isDir && !b.isDir) return -1;
                                    if (!a.isDir && b.isDir) return 1;
                                    return a.displayName.localeCompare(b.displayName);
                                })
                                .map(child => renderNode(child, isRoot ? 0 : depth + 1))}
                        </div>
                    )}
                </div>
            );
        }

        // Leaf File
        const isSelected = activeTabPath === node.path;
        const iconInfo = getFileIcon(node.displayName);
        const badge = getAgentBadge(node.attributed_agent, node.lane);

        return (
            <div
                key={node.path}
                onClick={() => handleOpenFile(node.path)}
                style={{ paddingLeft: `${depth * 12 + 18}px` }}
                className={`flex items-center justify-between py-1.5 px-2 cursor-pointer transition-colors group text-xs font-mono ${
                    isSelected
                        ? 'bg-[#37373d] text-white border-l-2 border-[#007acc]'
                        : 'text-gray-300 hover:bg-[#2a2d2e] hover:text-white'
                }`}
                title={`${node.path} (${(node.size / 1024).toFixed(1)} KB) - Agent: ${node.attributed_agent || 'Unknown'}`}
            >
                <div className="flex items-center gap-2 min-w-0">
                    <span className="text-sm shrink-0">{iconInfo.icon}</span>
                    <span className={`truncate ${isSelected ? 'font-medium text-white' : 'text-gray-300'}`}>
                        {node.displayName}
                    </span>
                    {node.is_recent && (
                        <span className="shrink-0 relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                        </span>
                    )}
                </div>

                <div className="flex items-center gap-1 shrink-0 ml-1.5">
                    {node.is_recent && (
                        <span className="text-[9px] uppercase tracking-wider font-bold px-1 py-0.2 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 scale-90">
                            MOD
                        </span>
                    )}
                    <span
                        className={`text-[9px] px-1.5 py-0.5 rounded border font-semibold ${badge.bg} ${badge.text} ${badge.border}`}
                    >
                        {badge.name.replace('Agent', '')}
                    </span>
                </div>
            </div>
        );
    };

    return (
        <div
            className={`fixed inset-0 z-[99999] flex items-center justify-center bg-black/85 backdrop-blur-md transition-all ${
                isFullscreen ? 'p-0' : 'p-2 sm:p-4 md:p-6'
            }`}
            onClick={(e) => {
                if (e.target === e.currentTarget) {
                    onClose();
                }
            }}
        >
            <div
                className={`bg-[#1e1e1e] border border-[#333333] shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9)] flex flex-col overflow-hidden text-gray-200 transition-all font-sans relative ${
                    isFullscreen
                        ? 'w-full h-full rounded-none border-none'
                        : 'w-full h-full sm:w-[98vw] md:w-[96vw] max-w-[1600px] sm:h-[96vh] md:h-[94vh] sm:rounded-lg md:rounded-xl'
                }`}
                onClick={(e) => e.stopPropagation()}
            >
                {/* ── VS Code Title Bar ────────────────────────────────────────── */}
                <div className="bg-[#323233] px-2.5 sm:px-3 py-1.5 sm:py-2 border-b border-[#252526] flex items-center justify-between select-none shrink-0 gap-2">
                    {/* Left: Window Dots & Title */}
                    <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                        {/* Sidebar toggle button (VS Code primary side bar icon) */}
                        <button
                            onClick={() => setSidebarOpen(prev => !prev)}
                            className={`p-1 rounded text-gray-400 hover:text-white hover:bg-[#3c3c3c] transition-colors ${
                                sidebarOpen ? 'text-[#007acc]' : ''
                            }`}
                            title={sidebarOpen ? 'Collapse Primary Side Bar (Ctrl+B)' : 'Expand Primary Side Bar (Ctrl+B)'}
                        >
                            {sidebarOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeft className="w-4 h-4" />}
                        </button>

                        <div className="hidden sm:flex items-center gap-1.5 shrink-0">
                            <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f56]" />
                            <div className="w-2.5 h-2.5 rounded-full bg-[#ffbd2e]" />
                            <div className="w-2.5 h-2.5 rounded-full bg-[#27c93f]" />
                        </div>

                        <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
                            <Code2 className="w-4 h-4 text-[#007acc] shrink-0" />
                            <span className="text-xs font-semibold tracking-wide text-gray-200 truncate hidden xs:inline sm:inline">
                                VS Code Swarm
                            </span>
                            <span
                                className="text-[10px] bg-[#3c3c3c] text-gray-300 px-1.5 sm:px-2 py-0.5 rounded font-mono truncate max-w-[100px] sm:max-w-[150px] md:max-w-none"
                                title={projectToken}
                            >
                                {projectToken.length > 12 ? `${projectToken.slice(0, 8)}...` : projectToken}
                            </span>
                        </div>
                    </div>

                    {/* Center: Live Agent Working Bar */}
                    <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
                        {activeAgents.length > 0 ? (
                            <div className="flex items-center gap-1.5 bg-[#252526] px-2 sm:px-3 py-1 rounded-full border border-gray-700">
                                <span className="relative flex h-2 w-2 shrink-0">
                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                                    <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
                                </span>
                                <span className="text-[11px] font-medium text-cyan-300 shrink-0">
                                    <span className="inline md:hidden">{activeAgents.length} Active</span>
                                    <span className="hidden md:inline">{activeAgents.length} Agents Working:</span>
                                </span>
                                <div className="hidden md:flex items-center gap-1.5">
                                    {activeAgents.map(a => (
                                        <span
                                            key={a.id}
                                            className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-[#37373d] text-gray-200 border border-gray-600 flex items-center gap-1"
                                        >
                                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                                            {a.name || a.id}
                                            {a.progress ? ` (${a.progress}%)` : ''}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        ) : (
                            <div className="hidden sm:flex items-center gap-1 text-[11px] text-gray-400 bg-[#252526] px-2.5 py-0.5 rounded-full">
                                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                                <span>Swarm Ready</span>
                            </div>
                        )}
                    </div>

                    {/* Right: Controls */}
                    <div className="flex items-center gap-1 sm:gap-1.5 shrink-0">
                        <button
                            onClick={() => setAutoPoll(!autoPoll)}
                            className={`flex items-center gap-1 text-[10px] sm:text-[11px] px-2 sm:px-2.5 py-1 rounded font-mono transition-colors ${
                                autoPoll
                                    ? 'bg-emerald-950/70 text-emerald-400 border border-emerald-800/80 hover:bg-emerald-900/80'
                                    : 'bg-gray-800 text-gray-400 border border-gray-700 hover:bg-gray-700'
                            }`}
                            title="Auto sync file changes every 2.5 seconds"
                        >
                            <Radio className={`w-3 h-3 ${autoPoll ? 'animate-pulse text-emerald-400' : 'text-gray-500'}`} />
                            <span className="hidden sm:inline">{autoPoll ? 'SYNC ON' : 'PAUSED'}</span>
                        </button>

                        <button
                            onClick={() => fetchWorkspaceFiles(false)}
                            className="p-1 sm:p-1.5 hover:bg-[#3c3c3c] text-gray-400 hover:text-white rounded transition-colors"
                            title="Refresh workspace files now"
                        >
                            <RefreshCw className={`w-3.5 h-3.5 ${loadingFiles ? 'animate-spin text-[#007acc]' : ''}`} />
                        </button>

                        <button
                            onClick={() => setIsFullscreen(!isFullscreen)}
                            className="hidden sm:block p-1 sm:p-1.5 hover:bg-[#3c3c3c] text-gray-400 hover:text-white rounded transition-colors"
                            title={isFullscreen ? 'Exit full screen' : 'Full screen'}
                        >
                            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                        </button>

                        <button
                            onClick={onClose}
                            className="flex items-center gap-1.5 px-3 py-1 bg-red-600/90 hover:bg-red-600 text-white rounded text-xs font-semibold shadow transition-colors ml-1"
                            title="Close Workspace (Esc)"
                        >
                            <X className="w-4 h-4" />
                            <span className="font-mono text-[11px] hidden xs:inline">Close (Esc)</span>
                        </button>
                    </div>
                </div>

                {/* ── Main Workspace Body (Sidebar + Editor) ─────────────────────── */}
                <div className="flex-1 flex overflow-hidden relative">
                    {/* ── Left Activity Bar ──────────────────────────────────────── */}
                    <div className="w-10 sm:w-12 bg-[#333333] flex flex-col items-center py-2 sm:py-3 gap-3 border-r border-[#252526] select-none shrink-0 z-20">
                        <button
                            onClick={() => handleActivityTabClick('explorer')}
                            className={`p-1.5 sm:p-2 rounded transition-colors ${
                                sidebarOpen && activeSidebarTab === 'explorer'
                                    ? 'text-white border-l-2 border-[#007acc] bg-[#252526]'
                                    : 'text-gray-400 hover:text-white'
                            }`}
                            title="Explorer (Click to toggle)"
                        >
                            <Folder className="w-4 h-4 sm:w-5 sm:h-5" />
                        </button>

                        <button
                            onClick={() => handleActivityTabClick('agents')}
                            className={`p-1.5 sm:p-2 rounded transition-colors relative ${
                                sidebarOpen && activeSidebarTab === 'agents'
                                    ? 'text-white border-l-2 border-[#007acc] bg-[#252526]'
                                    : 'text-gray-400 hover:text-white'
                            }`}
                            title="Agent Swarm Activity (Click to toggle)"
                        >
                            <Cpu className="w-4 h-4 sm:w-5 sm:h-5" />
                            {activeAgents.length > 0 && (
                                <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
                            )}
                        </button>

                        <div className="mt-auto flex flex-col items-center gap-3 text-gray-400">
                            <span className="text-[9px] font-mono text-gray-500 rotate-90 my-2 hidden sm:inline">SWARM</span>
                            <Terminal className="w-3.5 h-3.5 sm:w-4 sm:h-4 hover:text-white cursor-pointer" />
                        </div>
                    </div>

                    {/* ── Mobile Overlay Backdrop when Sidebar is Open ────────────── */}
                    {sidebarOpen && (
                        <div
                            className="md:hidden fixed inset-0 bg-black/60 z-20 backdrop-blur-xs"
                            onClick={() => setSidebarOpen(false)}
                        />
                    )}

                    {/* ── Left Sidebar (Explorer or Agent Panel) ─────────────────── */}
                    {sidebarOpen && (
                        <div className={`bg-[#252526] border-r border-[#1e1e1e] flex flex-col overflow-hidden shrink-0 z-30 transition-all ${
                            isMobile
                                ? 'absolute inset-y-0 left-10 sm:left-12 w-72 sm:w-80 max-w-[calc(100vw-3rem)] shadow-2xl'
                                : 'w-72 lg:w-80'
                        }`}>
                            {activeSidebarTab === 'explorer' ? (
                                <>
                                    {/* Explorer Header */}
                                    <div className="px-3 py-2 border-b border-[#1e1e1e] flex items-center justify-between select-none shrink-0">
                                        <div className="flex items-center gap-1.5">
                                            <span className="text-xs font-bold text-gray-400 tracking-wider uppercase font-mono">
                                                Explorer
                                            </span>
                                            <span className="text-[10px] text-gray-400 bg-[#333333] px-2 py-0.5 rounded-full font-mono">
                                                {files.length}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-1">
                                            {/* Close button on mobile */}
                                            {isMobile && (
                                                <button
                                                    onClick={() => setSidebarOpen(false)}
                                                    className="p-1 hover:bg-[#3c3c3c] text-gray-400 hover:text-white rounded"
                                                    title="Close Explorer"
                                                >
                                                    <X className="w-3.5 h-3.5" />
                                                </button>
                                            )}
                                        </div>
                                    </div>

                                    {/* Search Bar */}
                                    <div className="p-2 border-b border-[#1e1e1e] shrink-0">
                                        <div className="relative">
                                            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-gray-400" />
                                            <input
                                                type="text"
                                                value={searchQuery}
                                                onChange={e => setSearchQuery(e.target.value)}
                                                placeholder="Search files or agent..."
                                                className="w-full bg-[#1e1e1e] border border-gray-700 rounded pl-8 pr-2 py-1 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-[#007acc] font-mono"
                                            />
                                            {searchQuery && (
                                                <button
                                                    onClick={() => setSearchQuery('')}
                                                    className="absolute right-2 top-1.5 text-gray-400 hover:text-white"
                                                >
                                                    <X className="w-3 h-3" />
                                                </button>
                                            )}
                                        </div>
                                    </div>

                                    {/* File Tree Container */}
                                    <div className="flex-1 overflow-y-auto py-2">
                                        {loadingFiles && files.length === 0 ? (
                                            <div className="p-4 text-center text-xs text-gray-400 flex flex-col items-center gap-2">
                                                <RefreshCw className="w-4 h-4 animate-spin text-[#007acc]" />
                                                <span>Scanning workspace files...</span>
                                            </div>
                                        ) : files.length === 0 ? (
                                            <div className="p-4 text-center text-xs text-gray-400">
                                                No files found in workspace yet. Launch agents to start building!
                                            </div>
                                        ) : (
                                            renderNode(fileTree)
                                        )}
                                    </div>

                                    {/* Active Agent Summary in Sidebar Bottom */}
                                    <div className="p-2 bg-[#1e1e1e] border-t border-[#333333] shrink-0">
                                        <div className="text-[11px] font-semibold text-gray-400 mb-1 flex items-center justify-between">
                                            <span>Lane Attribution</span>
                                            <span className="text-[10px] text-gray-400">Live</span>
                                        </div>
                                        <div className="flex flex-wrap gap-1">
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-950/70 text-blue-300 border border-blue-800/60 font-mono">
                                                Backend: {files.filter(f => f.lane === 'backend').length}
                                            </span>
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-950/70 text-purple-300 border border-purple-800/60 font-mono">
                                                Frontend: {files.filter(f => f.lane === 'frontend').length}
                                            </span>
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-800/60 font-mono">
                                                QA: {files.filter(f => f.lane === 'qa').length}
                                            </span>
                                        </div>
                                    </div>
                                </>
                            ) : (
                                /* Agent Swarm Monitor Panel */
                                <div className="flex-1 flex flex-col overflow-hidden">
                                    <div className="px-3 py-2 border-b border-[#1e1e1e] flex items-center justify-between select-none shrink-0">
                                        <span className="text-xs font-bold text-gray-400 tracking-wider uppercase font-mono">
                                            Swarm Live State
                                        </span>
                                        <div className="flex items-center gap-1.5">
                                            <span className="text-[10px] text-emerald-400 bg-emerald-950/80 px-2 py-0.5 rounded font-mono">
                                                {activeAgents.length} Active
                                            </span>
                                            {isMobile && (
                                                <button
                                                    onClick={() => setSidebarOpen(false)}
                                                    className="p-1 hover:bg-[#3c3c3c] text-gray-400 hover:text-white rounded"
                                                >
                                                    <X className="w-3.5 h-3.5" />
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                    <div className="flex-1 overflow-y-auto p-3 space-y-3">
                                        {activeAgents.length === 0 ? (
                                            <div className="p-4 text-center text-xs text-gray-400 bg-[#1e1e1e] rounded border border-gray-800">
                                                No agents currently executing in containers. When you trigger "Run All", their live parallel work stream will display here.
                                            </div>
                                        ) : (
                                            activeAgents.map(a => {
                                                const badge = getAgentBadge(a.name || a.id);
                                                return (
                                                    <div
                                                        key={a.id}
                                                        className="bg-[#1e1e1e] border border-gray-700 rounded-lg p-2.5 sm:p-3 space-y-2"
                                                    >
                                                        <div className="flex items-center justify-between">
                                                            <div className="flex items-center gap-2">
                                                                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                                                                <span className="text-xs font-bold text-white font-mono">
                                                                    {a.name || a.id}
                                                                </span>
                                                            </div>
                                                            <span
                                                                className={`text-[10px] px-1.5 py-0.5 rounded border font-mono ${badge.bg} ${badge.text} ${badge.border}`}
                                                            >
                                                                {a.status}
                                                            </span>
                                                        </div>
                                                        <div className="text-[11px] text-gray-300 font-mono">
                                                            {a.progress_message || 'Executing assigned phase in workspace...'}
                                                        </div>
                                                        {typeof a.progress === 'number' && (
                                                            <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
                                                                <div
                                                                    className="bg-gradient-to-r from-blue-500 to-cyan-400 h-1.5 rounded-full transition-all duration-300"
                                                                    style={{ width: `${Math.min(100, Math.max(5, a.progress))}%` }}
                                                                />
                                                            </div>
                                                        )}
                                                    </div>
                                                );
                                            })
                                        )}

                                        {/* Recent modified files feed */}
                                        <div className="pt-2">
                                            <div className="text-xs font-semibold text-gray-400 mb-2 flex items-center gap-1.5">
                                                <Activity className="w-3.5 h-3.5 text-cyan-400" />
                                                <span>Recent File Activity</span>
                                            </div>
                                            <div className="space-y-1.5">
                                                {files
                                                    .filter(f => f.is_recent)
                                                    .slice(0, 8)
                                                    .map((rf, idx) => (
                                                        <div
                                                            key={idx}
                                                            onClick={() => handleOpenFile(rf.path)}
                                                            className="p-2 rounded bg-[#1e1e1e] hover:bg-[#2a2d2e] cursor-pointer border border-gray-800 transition-colors flex items-center justify-between text-xs font-mono"
                                                        >
                                                            <div className="truncate text-gray-300 max-w-[150px] sm:max-w-[170px]">
                                                                {rf.path}
                                                            </div>
                                                            <span className="text-[9px] text-emerald-400 bg-emerald-950/80 px-1 py-0.5 rounded">
                                                                {rf.attributed_agent}
                                                            </span>
                                                        </div>
                                                    ))}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* ── Center Editor Area ─────────────────────────────────────── */}
                    <div className="flex-1 flex flex-col bg-[#1e1e1e] overflow-hidden min-w-0">
                        {/* Editor Tabs Bar */}
                        <div className="bg-[#252526] border-b border-[#1e1e1e] flex items-center overflow-x-auto select-none no-scrollbar shrink-0">
                            {openTabs.length === 0 ? (
                                <div className="px-4 py-2 text-xs text-gray-500 italic">No files open</div>
                            ) : (
                                openTabs.map(tabPath => {
                                    const fileName = tabPath.split('/').pop();
                                    const isActive = tabPath === activeTabPath;
                                    const iconInfo = getFileIcon(fileName);
                                    const tabMeta = files.find(f => f.path === tabPath);

                                    return (
                                        <div
                                            key={tabPath}
                                            onClick={() => {
                                                setActiveTabPath(tabPath);
                                                if (!fileContentMap[tabPath]) fetchFileContent(tabPath);
                                            }}
                                            className={`flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-2 cursor-pointer border-r border-[#1e1e1e] transition-colors text-xs font-mono group shrink-0 ${
                                                isActive
                                                    ? 'bg-[#1e1e1e] text-white border-t-2 border-t-[#007acc]'
                                                    : 'bg-[#2d2d2d] text-gray-400 hover:bg-[#252526] hover:text-gray-200'
                                            }`}
                                        >
                                            <span className="shrink-0">{iconInfo.icon}</span>
                                            <span className="truncate max-w-[100px] sm:max-w-[140px]">{fileName}</span>
                                            {tabMeta?.is_recent && (
                                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" title="Modified recently" />
                                            )}
                                            <button
                                                onClick={(e) => handleCloseTab(tabPath, e)}
                                                className="text-gray-500 hover:text-white rounded p-0.5 opacity-60 group-hover:opacity-100 shrink-0 ml-1"
                                            >
                                                <X className="w-3 h-3" />
                                            </button>
                                        </div>
                                    );
                                })
                            )}
                        </div>

                        {/* Breadcrumbs & File Action Bar */}
                        {activeTabPath && (
                            <div className="bg-[#1e1e1e] px-2.5 sm:px-4 py-1.5 border-b border-[#2d2d2d] flex items-center justify-between text-xs font-mono select-none shrink-0 gap-2 overflow-x-auto no-scrollbar">
                                <div className="flex items-center gap-1 sm:gap-1.5 text-gray-400 min-w-0 truncate">
                                    <span className="text-gray-500 shrink-0">ws</span>
                                    {activeTabPath.split('/').map((part, idx, arr) => (
                                        <React.Fragment key={idx}>
                                            <ChevronRight className="w-3 h-3 text-gray-600 shrink-0" />
                                            <span
                                                className={`truncate ${
                                                    idx === arr.length - 1 ? 'text-gray-200 font-semibold' : 'text-gray-400'
                                                }`}
                                            >
                                                {part}
                                            </span>
                                        </React.Fragment>
                                    ))}

                                    {activeFileMeta?.attributed_agent && (
                                        <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-[#2a2d2e] text-cyan-300 border border-gray-700 hidden lg:inline shrink-0">
                                            {activeFileMeta.attributed_agent}
                                        </span>
                                    )}
                                </div>

                                <div className="flex items-center gap-1.5 shrink-0">
                                    {/* .env Secret Masking Toggle */}
                                    {isEnvFile && (
                                        <button
                                            onClick={() => setMaskSecrets(!maskSecrets)}
                                            className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] transition-colors ${
                                                maskSecrets
                                                    ? 'bg-amber-950/80 text-amber-300 border border-amber-800/80 hover:bg-amber-900/80'
                                                    : 'bg-[#2d2d2d] hover:bg-[#37373d] text-gray-300'
                                            }`}
                                            title={maskSecrets ? 'Masking active. Click to reveal credentials.' : 'Click to mask credentials in this .env file.'}
                                        >
                                            {maskSecrets ? <EyeOff className="w-3 h-3 text-amber-400" /> : <Eye className="w-3 h-3 text-emerald-400" />}
                                            <span className="hidden sm:inline font-mono">{maskSecrets ? 'Masked' : 'Reveal'}</span>
                                        </button>
                                    )}

                                    {/* Word Wrap Toggle */}
                                    <button
                                        onClick={() => setWordWrap(!wordWrap)}
                                        className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] transition-colors ${
                                            wordWrap
                                                ? 'bg-blue-950/80 text-blue-300 border border-blue-800/80'
                                                : 'bg-[#2d2d2d] hover:bg-[#37373d] text-gray-400'
                                        }`}
                                        title="Toggle Word Wrap (Alt+Z)"
                                    >
                                        <WrapText className="w-3 h-3" />
                                        <span className="hidden sm:inline font-mono">Wrap</span>
                                    </button>

                                    <button
                                        onClick={handleCopy}
                                        className="flex items-center gap-1 px-2 py-1 rounded bg-[#2d2d2d] hover:bg-[#37373d] text-gray-300 hover:text-white text-[11px] transition-colors"
                                        title="Copy code"
                                    >
                                        {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                                        <span className="hidden sm:inline">{copied ? 'Copied' : 'Copy'}</span>
                                    </button>

                                    <button
                                        onClick={handleDownload}
                                        className="flex items-center gap-1 px-2 py-1 rounded bg-[#2d2d2d] hover:bg-[#37373d] text-gray-300 hover:text-white text-[11px] transition-colors"
                                        title="Download file"
                                    >
                                        <Download className="w-3 h-3" />
                                        <span className="hidden sm:inline">Save</span>
                                    </button>

                                    <button
                                        onClick={() => fetchFileContent(activeTabPath)}
                                        className="p-1 sm:px-2 sm:py-1 rounded bg-[#2d2d2d] hover:bg-[#37373d] text-gray-300 hover:text-white text-[11px] transition-colors flex items-center gap-1"
                                        title="Reload file from disk"
                                    >
                                        <RefreshCw className={`w-3 h-3 ${loadingContent ? 'animate-spin' : ''}`} />
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* Editor Code Viewer */}
                        <div className="flex-1 overflow-auto bg-[#1e1e1e] relative font-mono text-xs sm:text-[13px] leading-relaxed">
                            {!activeTabPath ? (
                                <div className="h-full flex flex-col items-center justify-center text-gray-500 space-y-3 p-4 text-center">
                                    <Code2 className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600" />
                                    <p className="text-xs sm:text-sm">Select any file from the explorer on the left to preview.</p>
                                    <p className="text-[11px] sm:text-xs text-gray-600 max-w-sm">Files created and edited by Backend & Frontend swarm agents will appear here live.</p>
                                    {isMobile && !sidebarOpen && (
                                        <button
                                            onClick={() => setSidebarOpen(true)}
                                            className="px-3 py-1.5 bg-[#007acc] text-white rounded text-xs flex items-center gap-1.5 mt-2"
                                        >
                                            <Folder className="w-3.5 h-3.5" />
                                            Open Workspace Explorer
                                        </button>
                                    )}
                                </div>
                            ) : loadingContent && !activeContentData ? (
                                <div className="h-full flex items-center justify-center text-gray-400 gap-2 p-4 text-center text-xs sm:text-sm">
                                    <RefreshCw className="w-5 h-5 animate-spin text-[#007acc]" />
                                    <span>Reading file content from container workspace...</span>
                                </div>
                            ) : (
                                <div className="flex min-w-full">
                                    {/* Line Numbers Gutter */}
                                    <div className="bg-[#1e1e1e] select-none text-gray-600 text-right pr-2 sm:pr-4 pl-2 sm:pl-3 py-3 border-r border-[#2d2d2d] shrink-0 sticky left-0 z-10 font-mono text-[11px] sm:text-xs">
                                        {contentLines.map((_, i) => (
                                            <div key={i} className="leading-6 hover:text-gray-400">
                                                {i + 1}
                                            </div>
                                        ))}
                                    </div>

                                    {/* Code Content */}
                                    <div className="py-3 px-2 sm:px-4 flex-1 overflow-x-auto min-w-0">
                                        {contentLines.map((line, i) => (
                                            <div
                                                key={i}
                                                className={`leading-6 hover:bg-[#262626]/60 rounded px-1 ${
                                                    wordWrap ? 'break-words whitespace-pre-wrap' : 'whitespace-pre'
                                                }`}
                                            >
                                                {highlightLine(
                                                    line,
                                                    activeContentData?.language || (isEnvFile ? 'env' : ''),
                                                    maskSecrets
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* ── VS Code Bottom Status Bar ───────────────────────────────── */}
                <div className="bg-[#007acc] px-2.5 sm:px-3 py-1 flex items-center justify-between text-xs text-white select-none shrink-0 font-mono">
                    <div className="flex items-center gap-2 sm:gap-4 truncate">
                        <div className="flex items-center gap-1 hover:bg-[#1f8ad2] px-1 sm:px-1.5 py-0.5 rounded cursor-pointer shrink-0">
                            <GitBranch className="w-3 h-3 sm:w-3.5 sm:h-3.5" />
                            <span>main</span>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                            <Radio className="w-2.5 h-2.5 sm:w-3 sm:h-3 text-emerald-300 animate-pulse" />
                            <span className="hidden sm:inline">Swarm Sync: {autoPoll ? 'Active' : 'Paused'}</span>
                        </div>
                        {activeFileMeta?.attributed_agent && (
                            <div className="hidden sm:flex items-center gap-1 bg-[#0066aa] px-2 py-0.5 rounded text-[11px] shrink-0">
                                <span>Agent: {activeFileMeta.attributed_agent}</span>
                            </div>
                        )}
                    </div>

                    <div className="flex items-center gap-2 sm:gap-3 text-[10px] sm:text-[11px] shrink-0">
                        {activeContentData?.size ? (
                            <span className="hidden sm:inline">{(activeContentData.size / 1024).toFixed(1)} KB</span>
                        ) : null}
                        <span>L: {contentLines.length}</span>
                        <span className="hidden xs:inline sm:inline">UTF-8</span>
                        <span className="capitalize">{activeContentData?.language || (isEnvFile ? 'ENV' : 'Plain Text')}</span>
                        {lastSyncTime && (
                            <span className="text-blue-100 hidden md:inline">
                                {lastSyncTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                            </span>
                        )}
                        <button
                            onClick={onClose}
                            className="hover:bg-red-700/90 px-2 py-0.5 rounded text-[11px] font-mono flex items-center gap-1 text-white bg-[#005a9e] transition-colors ml-1 cursor-pointer"
                            title="Close Workspace (Esc)"
                        >
                            <X className="w-3 h-3" />
                            <span>Close</span>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
