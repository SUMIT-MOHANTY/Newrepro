import { useState, useEffect } from 'react';
import { 
    ChevronDown, ChevronRight, BookOpen, Zap, Shield, 
    Users, GitBranch, Brain, ArrowLeft, Search, 
    Smile, Meh, Frown, Menu, X, ExternalLink, Copy, Check,
    Sparkles, Sun, Moon,
    Home, Layers, FileUp, ShieldCheck, Database, ListTodo, UserPlus, Workflow, Cpu, Terminal, RefreshCw, Eye, GitPullRequest, Cable, Plug, DownloadCloud, HelpCircle
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import dsuiteLogo from '../assets/DSuite Gradient Ribbon Logo.png';

export default function Documentation() {
    const [theme, setTheme] = useState(localStorage.getItem('theme') || 'dark');
    const [currentArticle, setCurrentArticle] = useState('overview');
    const [isFeatureMappingOpen, setIsFeatureMappingOpen] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState([]);
    const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
    const [expandedAccordions, setExpandedAccordions] = useState({});
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
    const [copiedId, setCopiedId] = useState(null);
    const navigate = useNavigate();

    // Reset feedback and accordions when current article changes
    useEffect(() => {
        setFeedbackSubmitted(false);
        setExpandedAccordions({});
        setIsMobileMenuOpen(false);
        window.scrollTo(0, 0);
    }, [currentArticle]);

    // Handle theme sync and events
    useEffect(() => {
        const handleThemeChange = () => {
            setTheme(localStorage.getItem('theme') || 'dark');
        };
        window.addEventListener('theme-changed', handleThemeChange);
        return () => window.removeEventListener('theme-changed', handleThemeChange);
    }, []);

    const toggleTheme = () => {
        const newTheme = theme === 'dark' ? 'light' : 'dark';
        localStorage.setItem('theme', newTheme);
        setTheme(newTheme);
        if (newTheme === 'dark') {
            document.documentElement.classList.add('dark');
            document.documentElement.setAttribute('data-theme', 'dark');
        } else {
            document.documentElement.classList.remove('dark');
            document.documentElement.setAttribute('data-theme', 'light');
        }
        window.dispatchEvent(new Event('theme-changed'));
    };

    // Handle search query filtering
    useEffect(() => {
        if (!searchQuery.trim()) {
            setSearchResults([]);
            return;
        }
        const query = searchQuery.toLowerCase();
        const results = [];

        Object.entries(articles).forEach(([id, article]) => {
            if (
                article.title.toLowerCase().includes(query) ||
                article.subtitle.toLowerCase().includes(query) ||
                article.rawContent?.toLowerCase().includes(query)
            ) {
                results.push({ id, title: article.title, category: article.category });
            }
        });
        setSearchResults(results);
    }, [searchQuery]);

    // Toggle sub-section accordions
    const toggleAccordion = (id) => {
        setExpandedAccordions(prev => ({ ...prev, [id]: !prev[id] }));
    };

    // Copy text utility
    const handleCopy = (id, text) => {
        navigator.clipboard.writeText(text);
        setCopiedId(id);
        setTimeout(() => setCopiedId(null), 2000);
    };

    // Emojis rated click
    const handleFeedback = () => {
        setFeedbackSubmitted(true);
    };

    // Dynamic Style Tokens based on Theme
    const isLight = theme === 'light';
    const bgPage = isLight ? '#ffffff' : '#09090b';
    const bgSidebar = isLight ? '#f8fafc' : '#0c0c1e';
    const bgHeader = isLight ? '#ffffff' : '#0c0c1e';
    const borderCol = isLight ? '#e2e8f0' : 'rgba(139, 92, 246, 0.15)';
    const textMain = isLight ? '#334155' : '#cbd5e1';
    const textHeading = isLight ? '#0f172a' : '#f1f5f9';
    const textMuted = isLight ? '#64748b' : '#94a3b8';
    const bgCard = isLight ? '#ffffff' : 'rgba(30, 41, 59, 0.15)';
    const borderCard = isLight ? '#e2e8f0' : 'rgba(255, 255, 255, 0.05)';
    const bgSearch = isLight ? '#f1f5f9' : 'rgba(15, 15, 30, 0.6)';
    const borderSearch = isLight ? '#cbd5e1' : 'rgba(139, 92, 246, 0.2)';
    const textSearch = isLight ? '#1e293b' : '#f1f5f9';

    // Left Navigation Tree Structure
    const navigationTree = [
        {
            category: 'GETTING STARTED',
            items: [
                { id: 'overview', title: 'Platform Overview', icon: <Home size={16} /> },
                { id: 'quickstart', title: 'Quickstart Guide', icon: <Zap size={16} /> }
            ]
        },
        {
            category: 'FEATURE MAPPING',
            isCollapsible: true,
            subCategories: [
                {
                    category: 'USING DSUITE',
                    items: [
                        { id: 'brd-upload', title: 'BRD Upload & Ingestion', icon: <FileUp size={16} /> },
                        { id: 'governance', title: 'Governance Assessment', icon: <ShieldCheck size={16} /> },
                        { id: 'architecture', title: 'Tech Specs & ER Schemas', icon: <Database size={16} /> },
                        { id: 'task-planning', title: 'Task Planning & Backlog', icon: <ListTodo size={16} /> },
                        { id: 'resource-onboarding', title: 'Resource Onboarding', icon: <UserPlus size={16} /> },
                        { id: 'agent-coordination', title: 'Agent Coordination', icon: <Workflow size={16} /> }
                    ]
                },
                {
                    category: 'USING VIBECODING',
                    items: [
                        { id: 'spawning-agents', title: 'Spawning Worker Agents', icon: <Cpu size={16} /> },
                        { id: 'vibe-workspace', title: 'VibeCoding Workspace', icon: <Terminal size={16} /> },
                        { id: 'code-generation', title: 'Iterative Code Building', icon: <RefreshCw size={16} /> },
                        { id: 'live-preview', title: 'Live App Preview', icon: <Eye size={16} /> },
                        { id: 'git-delivery', title: 'Automated Git Release', icon: <GitPullRequest size={16} /> }
                    ]
                },
                {
                    category: 'INTEGRATION',
                    items: [
                        { id: 'dsuite-vibecoding', title: 'DSuite ↔ VibeCoding Integration', icon: <Cable size={16} /> },
                        { id: 'byo-agent-mcp', title: 'BYO Agent & MCP Support', icon: <Plug size={16} /> }
                    ]
                },
                {
                    category: 'SUPPORT',
                    items: [
                        { id: 'faq', title: 'Frequently Asked Questions', icon: <HelpCircle size={16} /> }
                    ]
                }
            ]
        }
    ];

    // Articles Content Database
    const articles = {
        overview: {
            category: 'GETTING STARTED',
            title: 'Platform Overview',
            subtitle: 'Welcome to the DSuite and VibeCoding developer ecosystem.',
            rawContent: 'DSuite is a framework. VibeCoding is the platform.',
            content: (
                <div>
                    <p style={{ fontSize: '16px', lineHeight: '1.8', color: textMain, marginBottom: '24px' }}>
                        DSuite and VibeCoding form a unified, AI-powered application development platform that takes business requirements and transforms them into live, production-ready systems.
                    </p>

                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                        gap: '24px',
                        marginTop: '32px',
                        marginBottom: '32px'
                    }}>
                        <div style={{
                            backgroundColor: isLight ? '#f8fafc' : 'rgba(139, 92, 246, 0.05)',
                            border: isLight ? '1px solid #e2e8f0' : '1px solid rgba(139, 92, 246, 0.15)',
                            borderRadius: '16px',
                            padding: '24px'
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                                <Shield size={24} color="#7c3aed" />
                                <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, margin: 0 }}>DSuite (Framework)</h3>
                            </div>
                            <p style={{ fontSize: '14px', lineHeight: '1.6', color: textMuted, margin: 0 }}>
                                Focuses on requirement screening, structural BRD analysis, governance assessment, technical stack specifications, database schemas, and sprint backlog task planning. It enables collaborative development through AI Assist and Coexistence modes where developers work in partnership with autonomous agents.
                            </p>
                        </div>

                        <div style={{
                            backgroundColor: isLight ? '#f8fafc' : 'rgba(236, 72, 153, 0.05)',
                            border: isLight ? '1px solid #e2e8f0' : '1px solid rgba(236, 72, 153, 0.15)',
                            borderRadius: '16px',
                            padding: '24px'
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                                <Zap size={24} color="#db2777" />
                                <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, margin: 0 }}>VibeCoding (The Platform)</h3>
                            </div>
                            <p style={{ fontSize: '14px', lineHeight: '1.6', color: textMuted, margin: 0 }}>
                                Focuses on spawn-to-execution sandbox management, automated Builder-Critic coding loops, live real-time progress logs, isolated environments, and automatic Git commits. It provides a direct VibeCoding mode where users can develop, modify, and build applications themselves.
                            </p>
                            <div style={{ marginTop: '12px' }}>
                                <a 
                                    href="https://sandbox1-dsuite.bourntec.com/vibecoding/"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: '4px',
                                        color: '#db2777',
                                        fontSize: '13px',
                                        fontWeight: '600',
                                        textDecoration: 'none'
                                    }}
                                    onMouseEnter={e => e.currentTarget.style.textDecoration = 'underline'}
                                    onMouseLeave={e => e.currentTarget.style.textDecoration = 'none'}
                                >
                                    Launch Vibecoding ↗
                                </a>
                            </div>
                        </div>
                    </div>

                    <h3 style={{ fontSize: '20px', fontWeight: '700', color: textHeading, marginTop: '40px', marginBottom: '16px' }}>Workflow Cycle</h3>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        The cycle starts when a user uploads a Business Requirements Document (BRD) into DSuite. From there, the platform determines the governance requirements, generates technical specifications, maps developer backlog items, and coordinates automated worker agents in VibeCoding to write, test, and release the code.
                    </p>
                </div>
            )
        },
        quickstart: {
            category: 'GETTING STARTED',
            title: 'Quickstart Guide',
            subtitle: 'Learn how to build your first application from a BRD in minutes.',
            rawContent: 'Upload requirements, answer governance, review analysis, approve task plan, start development.',
            content: (
                <div>
                    <p style={{ fontSize: '16px', lineHeight: '1.8', color: textMain, marginBottom: '24px' }}>
                        This quickstart guide helps you walk through the entire developer experience from requirements document to working code in minutes.
                    </p>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', margin: '32px 0' }}>
                        {[
                            { step: '1', title: 'Upload BRD', desc: 'Go to DSuite Dashboard and click "New Project". Upload your requirements as a PDF, DOCX, image, or enter a public URL.' },
                            { step: '2', title: 'Governance screening', desc: 'Answer the 17 governance questions. The system evaluates parameters like data sensitivity, APIs, and AI risks to classify the project path.' },
                            { step: '3', title: 'Review Tech Blueprint', desc: 'Inspect the generated ER database schema, architecture designs, Mermaid diagrams, and proposed file structures.' },
                            { step: '4', title: 'Task Creation', desc: 'Verify the automatically decomposed tasks according to requirements. Adjust timelines, dependencies, and checklist priorities.' },
                            { step: '5', title: 'Development', desc: 'Implement tasks through two choices: spawn autonomous worker agents to write and test code automatically, or build manually using the VibeCoding workspace.' },
                            { step: '6', title: 'Deploy', desc: 'Approve the verified codebase and let the platform package and deliver commits directly to your target GitHub/DevOps repository.' }
                        ].map((s, idx) => (
                            <div key={idx} style={{ 
                                display: 'flex', 
                                gap: '20px', 
                                backgroundColor: isLight ? '#f8fafc' : 'rgba(30, 41, 59, 0.25)', 
                                padding: '20px', 
                                borderRadius: '12px', 
                                border: isLight ? '1px solid #e2e8f0' : '1px solid rgba(255,255,255,0.05)' 
                            }}>
                                <div style={{
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    width: '36px', height: '36px', borderRadius: '50%',
                                    background: 'linear-gradient(135deg, #7c3aed 0%, #db2777 100%)',
                                    color: 'white', fontWeight: 'bold', fontSize: '16px', flexShrink: 0
                                }}>
                                    {s.step}
                                </div>
                                <div>
                                    <h4 style={{ fontSize: '16px', fontWeight: '700', color: textHeading, margin: '0 0 6px 0' }}>{s.title}</h4>
                                    <p style={{ fontSize: '14px', color: textMuted, margin: 0, lineHeight: '1.6' }}>{s.desc}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )
        },
        'brd-upload': {
            category: 'FEATURE MAPPING',
            title: 'BRD Ingestion & Ingest Flow',
            subtitle: 'Learn how DSuite screens and extracts architectural entities from requirement text.',
            rawContent: 'Upload formats, AI entity extraction, parsing, system boundaries.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        DSuite leverages a high-performance document parser to ingest multiple business requirements file formats. It extracts document content, tabular structures, and embedded visual schemas to prepare them for AI modeling.
                    </p>

                    <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, marginBottom: '16px' }}>Ingestion Engine Pipeline</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <AccordionCard 
                            id="ingest-engine" 
                            title="Core Ingestion Pipeline" 
                            isOpen={expandedAccordions['ingest-engine']} 
                            onToggle={() => toggleAccordion('ingest-engine')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                DSuite uses the <strong>Core Ingestion Pipeline</strong> to parse PDFs, DOCX files, PPTX decks, HTML files, and raw images. The parser analyzes layout hierarchies and outputs clean Markdown representation for downstream processing.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="ingest-text" 
                            title="Text & Tabular Structure Parsing" 
                            isOpen={expandedAccordions['ingest-text']} 
                            onToggle={() => toggleAccordion('ingest-text')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                During parsing, DSuite enables text extraction capabilities to read scanned images and documents. It also triggers advanced <strong>Table Structure Parsing</strong> to cleanly extract database schemas, Excel spreadsheets, or system configurations defined in tabular formats.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="ingest-multimodal" 
                            title="Multimodal Image Extraction" 
                            isOpen={expandedAccordions['ingest-multimodal']} 
                            onToggle={() => toggleAccordion('ingest-multimodal')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                DSuite extracts embedded image files, mockups, flowcharts, and architecture diagrams at high resolutions. These extracted pictures are passed directly to multimodal LLMs to analyze user interface requirements and system diagrams.
                            </p>
                        </AccordionCard>
                    </div>

                    <div style={{ marginTop: '24px' }}>
                        <div style={{ border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                            <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                                <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>BRD Ingestion Flow & Parser Pipeline</span>
                            </div>
                            <img src="/assets/docs/image15.png" alt="BRD Ingest Flow Pipeline" style={{ width: '100%', height: 'auto', display: 'block' }} />
                        </div>
                    </div>
                </div>
            )
        },
        governance: {
            category: 'FEATURE MAPPING',
            title: 'Governance Assessment',
            subtitle: 'Project path classification, risk parameters, and compliance scoring.',
            rawContent: 'Governance framework, 17 questions, 6 dimensions, hard stops, regulated data, AI risk.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        The DSuite Governance Framework assesses projects across 6 core dimensions using a 17-question assessment. The score determines if the code should run in a Sandbox, Controlled Sandbox, or Enterprise framework.
                    </p>

                    <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, marginBottom: '16px' }}>Evaluation Categories</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <AccordionCard 
                            id="gov-dimensions" 
                            title="The 6 Evaluation Dimensions" 
                            isOpen={expandedAccordions['gov-dimensions']} 
                            onToggle={() => toggleAccordion('gov-dimensions')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                1. <strong>Business Value & Urgency (20%)</strong>: Evaluates outcome impact, delay risks, and user counts.<br />
                                2. <strong>Data Sensitivity (25%)</strong>: Flags PII,financial data, credential storage, and LLM routes.<br />
                                3. <strong>Integration & Architecture Complexity (20%)</strong>: Assesses API integrations, external endpoints, and uptime SLAs.<br />
                                4. <strong>Operational Impact (15%)</strong>: Triggers on transaction reversibility and wrong output cost metrics.<br />
                                5. <strong>AI Risk (10%)</strong>: Measures autonomy level, decision-making rights, and logging auditing.<br />
                                6. <strong>Ownership & Support (10%)</strong>: Validates availability of named business owners and technical stewards.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="gov-scoring" 
                            title="Weighted Scoring Metrics & Thresholds" 
                            isOpen={expandedAccordions['gov-scoring']} 
                            onToggle={() => toggleAccordion('gov-scoring')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Each question is scored between 0 and 10. Weighted summation decides the project path:<br />
                                • <strong>Score &le; 3.5</strong>: <strong>Sandbox</strong> (Approved for high AI velocity with light guardrails).<br />
                                • <strong>Score 3.5 - 6.5</strong>: <strong>Controlled Sandbox / Fusion</strong> (Requires standard templates and manual checks before PR merge).<br />
                                • <strong>Score &gt; 6.5</strong>: <strong>Enterprise Build</strong> (Strict sandbox isolation and full IT/security oversight).
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="gov-stops" 
                            title="Hard Stop Constraints (Auto-Enterprise Escalation)" 
                            isOpen={expandedAccordions['gov-stops']} 
                            onToggle={() => toggleAccordion('gov-stops')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Triggering any of the following 5 conditions escalates the project instantly to <strong>Enterprise</strong> status:<br />
                                1. <strong>Regulated data hosted on internet-facing endpoints</strong>: Combining confidential/regulated fields with external routing.<br />
                                2. <strong>Irreversible transactions</strong>: Initiating irreversible deletions, approvals, or financial transfers.<br />
                                3. <strong>Production data stored in non-production environments</strong>.<br />
                                4. <strong>Confidential data sent to external public LLMs</strong>.<br />
                                5. <strong>No named Business Owner or Technical Steward</strong> configured in the system.
                            </p>
                        </AccordionCard>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', marginTop: '24px' }}>
                        <div style={{ border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                            <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                                <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>Governance Assessment Questionnaire</span>
                            </div>
                            <img src="/assets/docs/image7.png" alt="Governance Questionnaire" style={{ width: '100%', height: 'auto', display: 'block' }} />
                        </div>
                        <div style={{ border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                            <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                                <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>Scoring & Paths Classifications</span>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', padding: '12px', backgroundColor: isLight ? '#ffffff' : 'rgba(12, 12, 30, 0.4)' }}>
                                <div style={{ border: `1px solid ${borderCard}`, borderRadius: '8px', overflow: 'hidden', backgroundColor: '#ffffff' }}>
                                    <img src="/assets/docs/image20.png" alt="Governance assessment score" style={{ width: '100%', height: 'auto', display: 'block' }} />
                                </div>
                                <div style={{ border: `1px solid ${borderCard}`, borderRadius: '8px', overflow: 'hidden', backgroundColor: '#ffffff' }}>
                                    <img src="/assets/docs/image19.png" alt="Path Classification details" style={{ width: '100%', height: 'auto', display: 'block' }} />
                                </div>
                                <div style={{ border: `1px solid ${borderCard}`, borderRadius: '8px', overflow: 'hidden', backgroundColor: '#ffffff' }}>
                                    <img src="/assets/docs/image17.png" alt="Compliance parameters summary" style={{ width: '100%', height: 'auto', display: 'block' }} />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )
        },
        architecture: {
            category: 'FEATURE MAPPING',
            title: 'Technical Specifications & Design',
            subtitle: 'Automated database ER schema, file structural trees, and Mermaid specs.',
            rawContent: 'Database ER schema, relational schemas, technical specs, file structural trees, diagrams.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        DSuite automatically drafts technical specs so developers don't have to spend hours setting up base databases and directories.
                    </p>

                    <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, marginBottom: '16px' }}>Generated Specifications</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <AccordionCard 
                            id="spec-db" 
                            title="Entity Relationship & Database Schemas" 
                            isOpen={expandedAccordions['spec-db']} 
                            onToggle={() => toggleAccordion('spec-db')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Generates complete database models, table relationships, index configurations, and constraint logic tailored to the project's target database library.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="spec-files" 
                            title="File Structure Trees" 
                            isOpen={expandedAccordions['spec-files']} 
                            onToggle={() => toggleAccordion('spec-files')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Drafts a standard file directory structure. Ensures modular patterns (Controller-Service-Repository) are correctly organized before coding begins.
                            </p>
                        </AccordionCard>
                    </div>

                    <div style={{ marginTop: '24px', border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                            <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>Technical Specifications & Data Models Panel</span>
                        </div>
                        <img src="/assets/docs/screenshot_architecture.png" alt="Technical Specifications review" style={{ width: '100%', height: 'auto', display: 'block' }} />
                    </div>
                </div>
            )
        },
        'task-planning': {
            category: 'FEATURE MAPPING',
            title: 'Task Planning & Backlog Mapping',
            subtitle: 'Prioritizing sprint timelines and tracking requirements completion.',
            rawContent: 'Sprint planning, backlog, priorities, task breakdowns, milestones.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        DSuite automatically decomposes architectural requirements into structured backlog tickets, optimized for multi-agent parallel construction.
                    </p>

                    <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, marginBottom: '16px' }}>Decomposition Mechanics</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <AccordionCard 
                            id="task-grouping" 
                            title="Aggressive Layer-Based Grouping" 
                            isOpen={expandedAccordions['task-grouping']} 
                            onToggle={() => toggleAccordion('task-grouping')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Rather than dividing tasks by single user stories or features, DSuite groups tasks by <strong>layer boundaries</strong> (e.g. backend core model + endpoints as a single block; frontend views + routing as another block). This minimizes overlapping modifications, preventing merge conflicts when agents work simultaneously.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="task-limits" 
                            title="Scale Limits & Ticket Sizes" 
                            isOpen={expandedAccordions['task-limits']} 
                            onToggle={() => toggleAccordion('task-limits')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                To avoid over-fragmentation and redundant loops, DSuite enforces strict task limits based on project scale:<br />
                                • <strong>Simple projects</strong>: 4 - 6 tasks maximum.<br />
                                • <strong>Medium projects</strong>: 6 - 10 tasks maximum.<br />
                                • <strong>Complex microservices</strong>: 10 - 15 tasks maximum.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="task-wallet" 
                            title="Task Wallet Point System" 
                            isOpen={expandedAccordions['task-wallet']} 
                            onToggle={() => toggleAccordion('task-wallet')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Each ticket is assigned a complexity rating using a wallet weight: <strong>2, 3, 5, or 8 points</strong>. These points reflect the estimated scope and are used to allot agent run quotas and configure sprint allocation boundaries.
                            </p>
                        </AccordionCard>
                    </div>

                    <div style={{ marginTop: '24px', border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                            <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>Task Decomposition & Planning Board</span>
                        </div>
                        <img src="/assets/docs/image21.png" alt="Task Planning Dashboard" style={{ width: '100%', height: 'auto', display: 'block' }} />
                    </div>
                </div>
            )
        },
        'resource-onboarding': {
            category: 'USING DSUITE',
            title: 'Resource Onboarding & Allocation',
            subtitle: 'How to assign project members, define execution roles, and configure system permissions.',
            rawContent: 'Resource Onboarding, allocate team, role mappings, status dashboard.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        After tasks and architectural specifications are generated, the user should proceed to the Resource Onboarding section to assign project members, select roles, and specify execution permissions. Proper onboarding forms a bridge of secure execution boundaries for collaborative development between humans and AI agents.
                    </p>

                    <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, marginBottom: '16px' }}>Onboarding and Permissions</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <AccordionCard 
                            id="adding-resources" 
                            title="Adding Project Resources" 
                            isOpen={expandedAccordions['adding-resources']} 
                            onToggle={() => toggleAccordion('adding-resources')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Project administrators can onboard team members by selecting their directory profiles or entering their emails. Onboarded users receive secure invites to access workspace environments and sync hooks.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="resource-allocation" 
                            title="Resource Allocation & Roles" 
                            isOpen={expandedAccordions['resource-allocation']} 
                            onToggle={() => toggleAccordion('resource-allocation')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Define precise capabilities for project participants. Resources are mapped to specific roles (e.g. Developer, QA/Tester, Manager) to delegate write permissions, deployment capabilities, and review privileges.
                            </p>
                        </AccordionCard>
                    </div>

                    <div style={{ 
                        marginTop: '32px', 
                        border: `1px solid ${borderCard}`, 
                        borderRadius: '12px', 
                        backgroundColor: bgCard, 
                        overflow: 'hidden' 
                    }}>
                        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                            <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>Resource Onboarding Panel</span>
                        </div>
                        <img src="/assets/docs/image16.png" alt="Resource Onboarding Dashboard" style={{ width: '100%', height: 'auto', display: 'block' }} />
                    </div>
                </div>
            )
        },
        'agent-coordination': {
            category: 'FEATURE MAPPING',
            title: 'Agent Coordination & Delegation',
            subtitle: 'How DSuite orchestrates dedicated Dev, Test, and Deploy agent flows.',
            rawContent: 'DEV Agent, TEST Agent, DEPLOY Agent coordination, workflow, planning.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        DSuite serves as the orchestration backbone, dynamically managing workers, locks, and check-ins to enable conflict-free parallel code construction.
                    </p>

                    <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, marginBottom: '16px' }}>Orchestration Mechanics</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <AccordionCard 
                            id="dynamic-locks" 
                            title="Dynamic File & Directory Locking" 
                            isOpen={expandedAccordions['dynamic-locks']} 
                            onToggle={() => toggleAccordion('dynamic-locks')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                To prevent concurrent writes, the orchestration layer maintains a central registry of <strong>file locks</strong>. When a DEV agent begins construction on a backend module, it requests a lock. Other agents are blocked from modifying files in that subdirectory until the lock is released or a git checkpoint is pushed.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="coordination-syncs" 
                            title="Workflow Sync Checkpoints" 
                            isOpen={expandedAccordions['coordination-syncs']} 
                            onToggle={() => toggleAccordion('coordination-syncs')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                The orchestrator coordinates execution steps using specific sync checkpoints (e.g. `architecture_review` and `integration_checkpoint`). Agents must check in and wait until all dependent code layers compile successfully before merging changes.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="shared-context-sync" 
                            title="Enhanced Shared Context Hub" 
                            isOpen={expandedAccordions['shared-context-sync']} 
                            onToggle={() => toggleAccordion('shared-context-sync')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                A live context manager synchronizes code structures, database blueprints, global endpoints, and system constraints across active agents. As updates occur, they are streamed in real time, ensuring all agent workspaces have the same global awareness.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="agent-quota-kinds" 
                            title="Agent Allocation Kinds & Capacity Quotas" 
                            isOpen={expandedAccordions['agent-quota-kinds']} 
                            onToggle={() => toggleAccordion('agent-quota-kinds')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                DSuite manages agent capacity mapping and scaling limits at the organization level:<br />
                                • <strong>Shared vs. Dedicated Agents</strong>: Employs both shared agent nodes (distributed multi-tenant pools for general tasks) and dedicated agent resources (exclusively locked for sensitive enterprise pipelines).<br />
                                • <strong>Capacity Quota Limits</strong>: Tracks development capacity via organizational thresholds (`shared_quota` and `dedicated_quota`), capped individually for <strong>DEV</strong> and <strong>TEST</strong> agent subtypes.<br />
                                • <strong>Default Mappings</strong>: Allocates default preconfigured workers to projects instantly, scaling out to dedicated worker VMs as backlog ticket loads expand.
                            </p>
                        </AccordionCard>
                    </div>
                </div>
            )
        },
        'spawning-agents': {
            category: 'USING VIBECODING',
            title: 'Spawning Worker Agents',
            subtitle: 'Isolated sandbox scopes for Builder-Critic agent pools.',
            rawContent: 'Sandbox scopes, Builder-Critic, agent pools, environments, isolation.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        When coding starts, VibeCoding provisions isolated sandbox scopes for safety, resource throttling, and developer runtime setup.
                    </p>

                    <div style={{
                        marginBottom: '28px',
                        padding: '16px 20px',
                        borderRadius: '12px',
                        backgroundColor: isLight ? 'rgba(124, 58, 237, 0.04)' : 'rgba(139, 92, 246, 0.08)',
                        border: `1px solid ${isLight ? 'rgba(124, 58, 237, 0.12)' : 'rgba(139, 92, 246, 0.2)'}`,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '12px'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontSize: '18px' }}>🚀</span>
                            <h4 style={{ fontSize: '15px', fontWeight: '700', color: textHeading, margin: 0 }}>Try VibeCoding Sandbox Live</h4>
                        </div>
                        <p style={{ fontSize: '13px', color: textMuted, margin: 0, lineHeight: '1.6' }}>
                            Experience the hands-on code workspace firsthand. Boot isolated sandbox runs, write logic with autonomous assistant subagents, and test builds in real time.
                        </p>
                        <a 
                            href="https://sandbox1-dsuite.bourntec.com/vibecoding/"
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '6px',
                                padding: '8px 14px',
                                borderRadius: '6px',
                                background: 'linear-gradient(135deg, #7c3aed 0%, #db2777 100%)',
                                color: '#ffffff',
                                fontSize: '12px',
                                fontWeight: '700',
                                textDecoration: 'none',
                                alignSelf: 'flex-start',
                                marginTop: '4px',
                                boxShadow: '0 4px 12px rgba(124, 58, 237, 0.2)'
                            }}
                        >
                            Launch VibeCoding ↗
                        </a>
                    </div>

                    <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, marginBottom: '16px' }}>Agent Specifications & Sandbox Infrastructure</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <AccordionCard 
                            id="agent-runtime-spec" 
                            title="Sandbox Runtime Image Specifications" 
                            isOpen={expandedAccordions['agent-runtime-spec']} 
                            onToggle={() => toggleAccordion('agent-runtime-spec')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Worker agents execute within isolated, multi-language sandboxes. These environments are preconfigured with necessary compilers and runtime packages corresponding to the project blueprint, allowing fast dependency resolution and safe task compilation.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="agent-pools" 
                            title="Dev, Test, and Deploy Agent Roles" 
                            isOpen={expandedAccordions['agent-pools']} 
                            onToggle={() => toggleAccordion('agent-pools')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                • <strong>DEV Agent</strong>: Spawns with writing privileges to draft, modify, and build files inside the target code directories.<br />
                                • <strong>TEST Agent</strong>: Runs automated testing suites and checks terminal outputs to validate project acceptance criteria.<br />
                                • <strong>DEPLOY Agent</strong>: Packages compiled assets, audits libraries, and publishes release streams directly to destination repositories.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="agent-routing" 
                            title="Daemon Execution Model & Real-Time Logs" 
                            isOpen={expandedAccordions['agent-routing']} 
                            onToggle={() => toggleAccordion('agent-routing')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Workspaces are kept active using background execution daemons. Coordination controllers hook into sandbox terminals dynamically to trigger scripts, capture exit codes, and broadcast execution logs back to the dashboard in real time.
                            </p>
                        </AccordionCard>
                    </div>
                </div>
            )
        },
        'vibe-workspace': {
            category: 'USING VIBECODING',
            title: 'VibeCoding Workspace & AI Assistant',
            subtitle: 'Authoring applications using natural language prompts and interactive suggestions.',
            rawContent: 'VibeCoding workspace interface, Vibe Assistant sidebar, project manager, versions, suggestion cards, interactive prompt.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        The VibeCoding workspace provides a unified environment where developers can construct entire applications simply by describing them. The workspace integrates task triggers, code edits, and live preview panels into a single UI.
                    </p>

                    <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, marginBottom: '16px' }}>Workspace Components</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <AccordionCard 
                            id="vibe-assistant-sidebar" 
                            title="Interactive Vibe Assistant" 
                            isOpen={expandedAccordions['vibe-assistant-sidebar']} 
                            onToggle={() => toggleAccordion('vibe-assistant-sidebar')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Located on the right sidebar, the <strong>Vibe Assistant</strong> processes developer prompts in real time. It offers clickable suggestion cards (e.g., adding validation, error handling, or category milestones) to refine the code base step-by-step.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="vibe-workspace-auth" 
                            title="Platform Access & Project Registration" 
                            isOpen={expandedAccordions['vibe-workspace-auth']} 
                            onToggle={() => toggleAccordion('vibe-workspace-auth')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                New developers can register via the workspace landing page. Once authenticated, users can immediately spawn new projects or select existing codebases using the top project managers and version controllers.
                            </p>
                        </AccordionCard>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', marginTop: '24px' }}>
                        <div style={{ border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                            <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                                <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>VibeCoding Workspace Dashboard</span>
                            </div>
                            <img src="/assets/docs/vibe_image4.png" alt="VibeCoding Workspace Dashboard" style={{ width: '100%', height: 'auto', display: 'block' }} />
                        </div>
                        <div style={{ border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                            <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                                <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>VibeCoding Account Creation</span>
                            </div>
                            <img src="/assets/docs/vibe_image3.png" alt="VibeCoding Registration" style={{ width: '100%', height: 'auto', display: 'block' }} />
                        </div>
                        <div style={{ border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                            <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                                <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>Create New Project Dialogue</span>
                            </div>
                            <img src="/assets/docs/vibe_image6.png" alt="Create Project Modal" style={{ width: '100%', height: 'auto', display: 'block' }} />
                        </div>
                        <div style={{ border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                            <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                                <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>VibeCoding Landing Interface</span>
                            </div>
                            <img src="/assets/docs/vibe_image5.png" alt="VibeCoding Landing Page" style={{ width: '100%', height: 'auto', display: 'block' }} />
                        </div>
                    </div>
                </div>
            )
        },
        'code-generation': {
            category: 'USING VIBECODING',
            title: 'Iterative Code Building',
            subtitle: 'How Builder and Critic agents refine code blocks.',
            rawContent: 'Builder agent, critic agent, quality review, iterative refinement, code checking.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        VibeCoding uses a dual-agent check system. The Builder agent proposes code changes, and the Critic agent acts as a validator checking syntax, logic errors, and security issues.
                    </p>

                    <p style={{ fontSize: '14px', lineHeight: '1.6', color: textMain, marginBottom: '20px' }}>
                        The Builder proposes the codebase, the Critic identifies exceptions, and they loop until code is compiled successfully.
                    </p>

                    <div style={{ marginTop: '24px', border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                            <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>Iterative Code Building Workflow</span>
                        </div>
                        <img src="/assets/docs/vibe_image9.png" alt="Iterative Code Generation Progress" style={{ width: '100%', height: 'auto', display: 'block' }} />
                    </div>
                </div>
            )
        },
        'live-preview': {
            category: 'USING VIBECODING',
            title: 'Live App Preview',
            subtitle: 'Observing application builds inside sandbox iframe widgets.',
            rawContent: 'Live previews, sandbox environment, iframe widgets, real-time status logs.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        Once code is built, the server starts in development mode. The frontend embeds it in an iframe preview widget.
                    </p>

                    <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, marginBottom: '16px' }}>Interactive Sandbox Executions</h3>
                    <p style={{ fontSize: '14px', lineHeight: '1.6', color: textMain, marginBottom: '20px' }}>
                        The live application sandbox supports dynamic resizing (Desktop, Tablet, Mobile frames), hot reloading, and session snapshots to help test the running software immediately.
                    </p>

                    <div style={{ marginTop: '24px', border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                            <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>Running Application Live Preview (Age Calculator)</span>
                        </div>
                        <img src="/assets/docs/vibe_image7.png" alt="Application Live Preview" style={{ width: '100%', height: 'auto', display: 'block' }} />
                    </div>
                </div>
            )
        },
        'git-delivery': {
            category: 'USING VIBECODING',
            title: 'Automated Git Release',
            subtitle: 'Automating PR creation, branch management, and merges.',
            rawContent: 'Git sync, repository synchronization, branch management, commits, pull requests.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        VibeCoding commits code directly to your repository, creating clean, descriptive commits and auto-generating PR descriptions.
                    </p>

                    <div style={{ marginTop: '24px', border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                            <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>Automated Git Commit & PR Creation</span>
                        </div>
                        <img src="/assets/docs/vibe_image8.png" alt="Git Repository Commits and PR Delivery" style={{ width: '100%', height: 'auto', display: 'block' }} />
                    </div>
                </div>
            )
        },
        'dsuite-vibecoding': {
            category: 'INTEGRATION',
            title: 'DSuite ↔ VibeCoding Integration',
            subtitle: 'Learn how DSuite and VibeCoding coordinate planning and code execution.',
            rawContent: 'DSuite and VibeCoding unified workflow, token auth, real-time updates, data handoffs.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        The orchestrator framework (DSuite) and the execution platform (VibeCoding) are tightly integrated to create an end-to-end automated pipeline from business requirements to production code.
                    </p>

                    <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, marginBottom: '20px' }}>Unified Integration Workflow</h3>
                    
                    {/* Visual Stepper Diagram */}
                    <div style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '8px',
                        backgroundColor: isLight ? '#f8fafc' : 'rgba(255, 255, 255, 0.02)',
                        border: `1px solid ${borderCard}`,
                        borderRadius: '12px',
                        padding: '24px',
                        marginBottom: '32px'
                    }}>
                        {[
                            { step: '01', source: 'DSuite', label: 'BRD Ingestion', desc: 'Document parser extracts structural outlines, formatted text, and high-resolution picture diagrams.' },
                            { step: '02', source: 'DSuite', label: 'Governance Path & Blueprint', desc: '17-question engine classifies Sandbox vs. Enterprise path and outputs database schemas.' },
                            { step: '03', source: 'DSuite', label: 'Backlog Decomposition', desc: 'Sprint tickets generated with wallet complexity weights and strict architectural layer boundaries.' },
                            { step: '04', source: 'VibeCoding', label: 'Sandbox Provisioning', desc: 'Secure Sandboxes spin up and provision database schema migrations automatically.' },
                            { step: '05', source: 'VibeCoding', label: 'Builder-Critic Iterations', desc: 'Dev and Test agents modify files matching backlog items, refactoring code until checks pass.' },
                            { step: '06', source: 'VibeCoding', label: 'PR Delivery & Release', desc: 'Auto-merges verified changes and creates clean git commits to delivery repositories.' }
                        ].map((item, idx) => (
                            <div key={idx} style={{ display: 'flex', flexDirection: 'column' }}>
                                <div style={{
                                    display: 'flex',
                                    alignItems: 'flex-start',
                                    gap: '16px',
                                    padding: '12px',
                                    borderRadius: '8px',
                                    transition: 'all 0.2s',
                                    cursor: 'default'
                                }}
                                onMouseEnter={(e) => {
                                    e.currentTarget.style.backgroundColor = isLight ? '#f1f5f9' : 'rgba(139, 92, 246, 0.04)';
                                }}
                                onMouseLeave={(e) => {
                                    e.currentTarget.style.backgroundColor = 'transparent';
                                }}
                                >
                                    <div style={{
                                        width: '32px',
                                        height: '32px',
                                        borderRadius: '8px',
                                        backgroundColor: item.source === 'DSuite' ? '#7c3aed' : '#db2777',
                                        color: '#ffffff',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        fontSize: '13px',
                                        fontWeight: 'bold',
                                        flexShrink: 0
                                    }}>
                                        {item.step}
                                    </div>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                            <span style={{ fontSize: '15px', fontWeight: '700', color: textHeading }}>{item.label}</span>
                                            <span style={{
                                                fontSize: '10px',
                                                fontWeight: 'bold',
                                                textTransform: 'uppercase',
                                                padding: '2px 6px',
                                                borderRadius: '4px',
                                                backgroundColor: item.source === 'DSuite' ? 'rgba(124, 58, 237, 0.1)' : 'rgba(219, 39, 119, 0.1)',
                                                color: item.source === 'DSuite' ? '#7c3aed' : '#db2777'
                                            }}>{item.source}</span>
                                        </div>
                                        <p style={{ margin: '4px 0 0 0', color: textMuted, fontSize: '13px', lineHeight: '1.5' }}>{item.desc}</p>
                                    </div>
                                </div>
                                {idx < 5 && (
                                    <div style={{
                                        width: '2px',
                                        height: '16px',
                                        backgroundColor: isLight ? '#e2e8f0' : 'rgba(255, 255, 255, 0.05)',
                                        marginLeft: '27px',
                                        marginTop: '4px',
                                        marginBottom: '4px'
                                    }}></div>
                                )}
                            </div>
                        ))}
                    </div>
                    
                    <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, marginBottom: '16px' }}>Shared Integration Elements</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <AccordionCard 
                            id="int-auth" 
                            title="Authentication & Handshake" 
                            isOpen={expandedAccordions['int-auth']} 
                            onToggle={() => toggleAccordion('int-auth')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                The orchestrator and platform communicate using secure authorization tokens signed by the system master keys. This ensures that only authorized runners can request task parameters or push git delivery streams.
                            </p>
                        </AccordionCard>
                        
                        <AccordionCard 
                            id="int-sync" 
                            title="Real-Time Synchronization" 
                            isOpen={expandedAccordions['int-sync']} 
                            onToggle={() => toggleAccordion('int-sync')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                VibeCoding sandboxes stream live compilation and test progress updates back to the DSuite database via persistent event streams, updating user dashboard backlog interfaces in real time.
                            </p>
                        </AccordionCard>
                    </div>
                </div>
            )
        },
        'byo-agent-mcp': {
            category: 'INTEGRATION',
            title: 'Bring Your Own Agent & MCP Server Integration',
            subtitle: 'Registering custom agent runners and connecting Model Context Protocol tools.',
            rawContent: 'BYO Agent, Bring Your Own Agent, MCP server, Model Context Protocol, integrations.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        DSuite and VibeCoding allow developers to expand the default execution environment by registering custom external agents and hooking in Model Context Protocol (MCP) server endpoints.
                    </p>

                    <h3 style={{ fontSize: '18px', fontWeight: '700', color: textHeading, marginBottom: '16px' }}>Integration Models</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <AccordionCard 
                            id="byo-agent-specs" 
                            title="Bring Your Own Agent (BYOA)" 
                            isOpen={expandedAccordions['byo-agent-specs']} 
                            onToggle={() => toggleAccordion('byo-agent-specs')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Register your custom agents (e.g. built using LangChain, CrewAI, or proprietary scripts) into the VibeCoding pool. By exposing standard real-time event hooks and adhering to DSuite's dynamic file-locking protocol, custom agents can pick up backlog tickets and write code alongside system workers.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="mcp-protocol" 
                            title="Model Context Protocol (MCP) Server Support" 
                            isOpen={expandedAccordions['mcp-protocol']} 
                            onToggle={() => toggleAccordion('mcp-protocol')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Connect local or remote MCP servers to expose external tools, enterprise database connectors, or filesystem access directly to coding agents. This allows agents to query live metadata or run terminal scripts on external developer setups safely.
                            </p>
                        </AccordionCard>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', marginTop: '24px' }}>
                        {/* Side-by-side box for MCP Config and Active Clients */}
                        <div style={{ display: 'flex', flexDirection: 'row', flexWrap: 'wrap', gap: '16px' }}>
                            <div style={{ flex: '1 1 300px', border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                                <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                                    <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>Model Context Protocol (MCP) Servers Config</span>
                                </div>
                                <img src="/assets/docs/mcp_image1.png" alt="MCP Servers configuration" style={{ width: '100%', height: 'auto', display: 'block' }} />
                            </div>

                            <div style={{ flex: '1 1 300px', border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                                <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                                    <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>Active MCP Clients Setup & Tool Registry</span>
                                </div>
                                <img src="/assets/docs/mcp_image2.png" alt="MCP Active Clients and Tools" style={{ width: '100%', height: 'auto', display: 'block' }} />
                            </div>
                        </div>

                        <div style={{ border: `1px solid ${borderCard}`, borderRadius: '12px', overflow: 'hidden' }}>
                            <div style={{ padding: '12px 16px', borderBottom: `1px solid ${borderCard}`, backgroundColor: isLight ? '#f8fafc' : 'rgba(255,255,255,0.02)' }}>
                                <span style={{ fontSize: '13px', fontWeight: '600', color: textHeading }}>Plugins & Tools Integrations Overview</span>
                            </div>
                            <img src="/assets/docs/image16.png" alt="Plugins Configuration Panel" style={{ width: '100%', height: 'auto', display: 'block' }} />
                        </div>
                    </div>
                </div>
            )
        },
        'faq': {
            category: 'SUPPORT',
            title: 'Frequently Asked Questions',
            subtitle: 'Answers to common architectural, integration, and coordination questions.',
            rawContent: 'FAQ, frequently asked questions, isolation support, agent configurations, help.',
            content: (
                <div>
                    <p style={{ fontSize: '15px', lineHeight: '1.7', color: textMain, marginBottom: '24px' }}>
                        Find answers to common questions about the DSuite framework and VibeCoding platform capabilities below.
                    </p>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <AccordionCard 
                            id="faq-1" 
                            title="How does DSuite differ from traditional sprint planning boards?" 
                            isOpen={expandedAccordions['faq-1']} 
                            onToggle={() => toggleAccordion('faq-1')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                DSuite does not simply list tasks; it actively screens requirements for risk, drafts database ER diagrams, compiles target directory blueprints, enforces architectural boundaries, and directly allocates tasks to autonomous coding agents for end-to-end builds.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="faq-2" 
                            title="How is sandbox environment safety and isolation handled?" 
                            isOpen={expandedAccordions['faq-2']} 
                            onToggle={() => toggleAccordion('faq-2')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                All agent runs, test executions, and builds occur inside isolated, multi-language sandboxes. These sandbox scopes constrain execution privileges, protecting developer file structures and staging deployments from unauthorized mutations.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="faq-3" 
                            title="Can developers edit project files manually during agent execution?" 
                            isOpen={expandedAccordions['faq-3']} 
                            onToggle={() => toggleAccordion('faq-3')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Yes. The coexistence model allows developers to write code alongside active agents. The central coordination registry locks specific subdirectories dynamically to prevent file overwrite collisions while developers modify code.
                            </p>
                        </AccordionCard>

                        <AccordionCard 
                            id="faq-4" 
                            title="What external LLMs or agent systems can I connect?" 
                            isOpen={expandedAccordions['faq-4']} 
                            onToggle={() => toggleAccordion('faq-4')}
                            theme={theme}
                        >
                            <p style={{ margin: 0, color: textMuted, fontSize: '14px', lineHeight: '1.6' }}>
                                Through standard integration interfaces, you can hook in external agent frameworks (Bring Your Own Agent model) or connect local/remote Model Context Protocol (MCP) servers to expose proprietary databases and filesystem commands.
                            </p>
                        </AccordionCard>
                    </div>
                </div>
            )
        }
    };

    // Calculate previous and next articles for navigation cards
    const flatArticles = navigationTree.flatMap(cat => cat.subCategories ? cat.subCategories.flatMap(sub => sub.items) : cat.items);
    const currentIndex = flatArticles.findIndex(item => item.id === currentArticle);
    const previousArticle = currentIndex > 0 ? flatArticles[currentIndex - 1] : null;
    const nextArticle = currentIndex < flatArticles.length - 1 ? flatArticles[currentIndex + 1] : null;

    const currentArticleData = articles[currentArticle] || articles.overview;

    return (
        <div style={{
            backgroundColor: bgPage,
            color: textMain,
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            fontFamily: 'system-ui, -apple-system, sans-serif',
            transition: 'background-color 0.2s, color 0.2s'
        }}>
            {/* Top Navbar */}
            <header style={{
                height: '64px',
                borderBottom: `1px solid ${borderCol}`,
                backgroundColor: bgHeader,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0 24px',
                position: 'sticky',
                top: 0,
                zIndex: 40,
                transition: 'background-color 0.2s, border-color 0.2s'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <button 
                        onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                        style={{
                            alignItems: 'center',
                            backgroundColor: 'transparent',
                            border: 'none',
                            color: '#7c3aed',
                            cursor: 'pointer',
                            padding: '4px',
                            borderRadius: '6px',
                            display: 'none', // Overridden in responsive view below
                        }}
                        className="mobile-hamburger-btn"
                    >
                        {isMobileMenuOpen ? <X size={22} /> : <Menu size={22} />}
                    </button>
                    
                    <div 
                        onClick={() => navigate('/')}
                        style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}
                    >
                        <img 
                            src={dsuiteLogo} 
                            alt="DSuite Logo" 
                            style={{ height: '30px', width: 'auto', display: 'block', marginRight: '6px' }} 
                        />
                        <span style={{ 
                            fontWeight: '800', 
                            letterSpacing: '0.05em', 
                            fontSize: '15px', 
                            background: 'linear-gradient(to right, #8b5cf6, #ec4899)',
                            WebkitBackgroundClip: 'text',
                            WebkitTextFillColor: 'transparent',
                            lineHeight: '1', 
                            transform: 'translateY(1px)', 
                            display: 'inline-block' 
                        }}>
                            DSuite
                        </span>
                    </div>
                </div>

                {/* Header links, Search & Theme Toggle */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                    <nav style={{ display: 'flex', alignItems: 'center', gap: '12px' }} className="nav-desktop-links">
                        <button onClick={() => navigate('/')} style={{ ...navHeaderLinkStyle, color: textMuted }}>Home</button>
                        <button onClick={() => navigate('/login')} style={{ ...navHeaderLinkStyle, color: textMuted }}>Login</button>
                        <button onClick={() => navigate('/dashboard')} style={{ ...navHeaderLinkStyle, color: textMuted }}>Dashboard</button>
                    </nav>

                    {/* Theme Toggle */}
                    <button 
                        onClick={toggleTheme}
                        style={{
                            backgroundColor: 'transparent',
                            border: 'none',
                            color: textMuted,
                            cursor: 'pointer',
                            padding: '6px',
                            borderRadius: '8px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            transition: 'background-color 0.2s, color 0.2s'
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = isLight ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.04)'}
                        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                    >
                        {isLight ? <Moon size={18} /> : <Sun size={18} />}
                    </button>

                    {/* Search Input Mock */}
                    <div style={{ position: 'relative', width: '200px' }} className="nav-search-bar">
                        <Search size={14} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#64748b' }} />
                        <input
                            type="text"
                            placeholder="Search Docs..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            style={{
                                width: '100%',
                                backgroundColor: bgSearch,
                                border: `1px solid ${borderSearch}`,
                                borderRadius: '8px',
                                padding: '8px 12px 8px 34px',
                                fontSize: '13px',
                                color: textSearch,
                                outline: 'none',
                                transition: 'background-color 0.2s, border-color 0.2s, color 0.2s'
                            }}
                        />
                        {searchResults.length > 0 && (
                            <div style={{
                                position: 'absolute',
                                right: 0,
                                top: '42px',
                                width: '280px',
                                backgroundColor: bgHeader,
                                border: `1px solid ${borderCol}`,
                                borderRadius: '8px',
                                boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1)',
                                padding: '8px 0',
                                maxHeight: '300px',
                                overflowY: 'auto'
                            }}>
                                {searchResults.map(result => (
                                    <div 
                                        key={result.id}
                                        onClick={() => {
                                            setCurrentArticle(result.id);
                                            setSearchQuery('');
                                        }}
                                        style={{
                                            padding: '8px 16px',
                                            cursor: 'pointer',
                                            fontSize: '13px',
                                            transition: 'background-color 0.2s',
                                            textAlign: 'left'
                                        }}
                                        onMouseEnter={(e) => e.target.style.backgroundColor = 'rgba(124, 58, 237, 0.08)'}
                                        onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                                    >
                                        <div style={{ fontSize: '10px', color: '#7c3aed', fontWeight: 'bold', textTransform: 'uppercase' }}>
                                            {result.category}
                                        </div>
                                        <div style={{ color: textHeading, marginTop: '2px' }}>{result.title}</div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </header>

            {/* Layout Wrapper */}
            <div style={{ display: 'flex', flex: 1, position: 'relative' }}>
                
                {/* Left Navigation Sidebar */}
                <aside 
                    style={{
                        width: '280px',
                        borderRight: `1px solid ${borderCol}`,
                        backgroundColor: bgSidebar,
                        padding: '32px 16px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        height: 'calc(100vh - 64px)',
                        position: 'sticky',
                        top: '64px',
                        overflowY: 'auto',
                        zIndex: 30,
                        transition: 'background-color 0.2s, border-color 0.2s'
                    }}
                    className={`docs-sidebar ${isMobileMenuOpen ? 'mobile-open' : ''}`}
                >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
                        {navigationTree.map((cat, catIdx) => {
                            const renderItems = (items, isSub = false) => (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', paddingLeft: isSub ? '12px' : '0' }}>
                                    {items.map(item => {
                                        const isActive = item.id === currentArticle;
                                        return (
                                            <button
                                                key={item.id}
                                                onClick={() => setCurrentArticle(item.id)}
                                                style={{
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: '12px',
                                                    width: '100%',
                                                    padding: '8px 12px',
                                                    borderRadius: '8px',
                                                    border: 'none',
                                                    backgroundColor: isActive ? (isLight ? 'rgba(124, 58, 237, 0.08)' : 'rgba(139, 92, 246, 0.1)') : 'transparent',
                                                    color: isActive ? (isLight ? '#7c3aed' : '#a78bfa') : textMuted,
                                                    fontSize: '13px',
                                                    fontWeight: isActive ? '700' : '500',
                                                    cursor: 'pointer',
                                                    transition: 'all 0.2s',
                                                    textAlign: 'left',
                                                    borderLeft: isActive ? (isLight ? '3px solid #7c3aed' : '3px solid #8b5cf6') : '3px solid transparent',
                                                    borderTopLeftRadius: 0,
                                                    borderBottomLeftRadius: 0
                                                }}
                                                onMouseEnter={(e) => {
                                                    if (!isActive) {
                                                        e.target.style.backgroundColor = isLight ? 'rgba(124, 58, 237, 0.04)' : 'rgba(139, 92, 246, 0.04)';
                                                        e.target.style.color = isLight ? '#0f172a' : '#cbd5e1';
                                                    }
                                                }}
                                                onMouseLeave={(e) => {
                                                    if (!isActive) {
                                                        e.target.style.backgroundColor = 'transparent';
                                                        e.target.style.color = textMuted;
                                                    }
                                                }}
                                            >
                                                {item.icon}
                                                <span>{item.title}</span>
                                            </button>
                                        );
                                    })}
                                </div>
                            );

                            if (cat.isCollapsible) {
                                return (
                                    <div key={catIdx} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                        <button 
                                            onClick={() => setIsFeatureMappingOpen(!isFeatureMappingOpen)}
                                            style={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'space-between',
                                                width: '100%',
                                                backgroundColor: 'transparent',
                                                border: 'none',
                                                cursor: 'pointer',
                                                padding: '4px 8px',
                                                textAlign: 'left',
                                                margin: '0 0 4px 0'
                                            }}
                                        >
                                            <span style={{
                                                fontSize: '11px',
                                                fontWeight: '800',
                                                color: '#64748b',
                                                letterSpacing: '0.08em',
                                                textTransform: 'uppercase'
                                            }}>
                                                {cat.category}
                                            </span>
                                            <ChevronDown size={14} color="#64748b" style={{
                                                transform: isFeatureMappingOpen ? 'none' : 'rotate(-90deg)',
                                                transition: 'transform 0.2s'
                                            }} />
                                        </button>
                                        {isFeatureMappingOpen && (
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', borderLeft: `1px solid ${borderCol}`, marginLeft: '12px', paddingLeft: '4px' }}>
                                                {cat.subCategories.map((sub, subIdx) => (
                                                    <div key={subIdx} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                                        <span style={{
                                                            fontSize: '10px',
                                                            fontWeight: '700',
                                                            color: isLight ? '#7c3aed' : '#a78bfa',
                                                            letterSpacing: '0.05em',
                                                            margin: '0 0 2px 12px',
                                                            textTransform: 'uppercase',
                                                            opacity: 0.8
                                                        }}>
                                                            {sub.category}
                                                        </span>
                                                        {renderItems(sub.items, true)}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                );
                            }

                            return (
                                <div key={catIdx} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                    <h3 style={{
                                        fontSize: '11px',
                                        fontWeight: '800',
                                        color: '#64748b',
                                        letterSpacing: '0.08em',
                                        margin: '0 0 4px 8px',
                                        textTransform: 'uppercase'
                                    }}>
                                        {cat.category}
                                    </h3>
                                    {renderItems(cat.items)}
                                </div>
                            );
                        })}
                    </div>

                    {/* Badge Mock */}
                    <div style={{
                        marginTop: '32px',
                        padding: '12px 16px',
                        borderRadius: '10px',
                        backgroundColor: isLight ? '#f1f5f9' : 'rgba(255, 255, 255, 0.02)',
                        border: `1px solid ${borderCard}`,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px',
                        fontSize: '12px',
                        color: '#64748b'
                    }}>
                        <BookOpen size={16} />
                        <span>Powered by DSuite Docs</span>
                    </div>
                </aside>

                {/* Main Content Area */}
                <main style={{
                    flex: 1,
                    padding: '32px 48px',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    overflowY: 'auto'
                }}>
                    <div style={{ width: '100%', maxWidth: '960px', textAlign: 'left' }}>
                        
                        {/* Breadcrumbs */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', fontWeight: '800', color: '#7c3aed', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                            <span>DOCS</span>
                            <ChevronRight size={12} />
                            <span>{currentArticleData.category}</span>
                        </div>

                        {/* Title */}
                        <h1 style={{ fontSize: '32px', fontWeight: '800', color: textHeading, margin: '0 0 8px 0', letterSpacing: '-0.02em' }}>
                            {currentArticleData.title}
                        </h1>

                        {/* Subtitle / Tagline */}
                        <p style={{ fontSize: '16px', color: textMuted, margin: '0 0 16px 0', lineHeight: '1.5', fontWeight: '400' }}>
                            {currentArticleData.subtitle}
                        </p>

                        <div style={{ borderBottom: `1px solid ${borderCol}`, marginBottom: '20px' }}></div>

                        {/* Dynamic Article Page Content */}
                        <div style={{ minHeight: '300px' }}>
                            {currentArticleData.content}
                        </div>

                        <div style={{ borderBottom: `1px solid ${borderCol}`, marginTop: '48px', marginBottom: '32px' }}></div>

                        {/* Footer navigation links */}
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                            gap: '16px',
                            marginBottom: '48px'
                        }}>
                            {previousArticle ? (
                                <div 
                                    onClick={() => setCurrentArticle(previousArticle.id)}
                                    style={{
                                        backgroundColor: bgCard,
                                        border: `1px solid ${borderCard}`,
                                        borderRadius: '12px',
                                        padding: '20px',
                                        cursor: 'pointer',
                                        transition: 'all 0.2s'
                                    }}
                                    onMouseEnter={(e) => {
                                        e.currentTarget.style.borderColor = '#7c3aed';
                                        e.currentTarget.style.backgroundColor = isLight ? '#f8fafc' : 'rgba(139, 92, 246, 0.02)';
                                    }}
                                    onMouseLeave={(e) => {
                                        e.currentTarget.style.borderColor = borderCard;
                                        e.currentTarget.style.backgroundColor = bgCard;
                                    }}
                                >
                                    <div style={{ fontSize: '11px', color: '#7c3aed', fontWeight: 'bold' }}>PREVIOUS</div>
                                    <div style={{ fontSize: '15px', color: textHeading, fontWeight: '700', marginTop: '4px' }}>{previousArticle.title}</div>
                                </div>
                            ) : <div />}

                            {nextArticle ? (
                                <div 
                                    onClick={() => setCurrentArticle(nextArticle.id)}
                                    style={{
                                        backgroundColor: bgCard,
                                        border: `1px solid ${borderCard}`,
                                        borderRadius: '12px',
                                        padding: '20px',
                                        cursor: 'pointer',
                                        transition: 'all 0.2s',
                                        textAlign: 'right'
                                    }}
                                    onMouseEnter={(e) => {
                                        e.currentTarget.style.borderColor = '#7c3aed';
                                        e.currentTarget.style.backgroundColor = isLight ? '#f8fafc' : 'rgba(139, 92, 246, 0.02)';
                                    }}
                                    onMouseLeave={(e) => {
                                        e.currentTarget.style.borderColor = borderCard;
                                        e.currentTarget.style.backgroundColor = bgCard;
                                    }}
                                >
                                    <div style={{ fontSize: '11px', color: '#7c3aed', fontWeight: 'bold' }}>NEXT</div>
                                    <div style={{ fontSize: '15px', color: textHeading, fontWeight: '700', marginTop: '4px' }}>{nextArticle.title}</div>
                                </div>
                            ) : <div />}
                        </div>

                        {/* Page Footer feedback & timestamp */}
                        <div style={{
                            display: 'flex',
                            flexWrap: 'wrap',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: '24px',
                            paddingTop: '24px',
                            borderTop: `1px solid ${borderCol}`,
                            color: '#64748b',
                            fontSize: '13px'
                        }}>
                            <div>Last updated 2 days ago</div>
                            
                            {/* Was this helpful ratings */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                <span>Was this helpful?</span>
                                {feedbackSubmitted ? (
                                    <span style={{ color: '#10b981', fontWeight: 'bold' }}>Thank you for your feedback!</span>
                                ) : (
                                    <div style={{ display: 'flex', gap: '6px' }}>
                                        <button onClick={handleFeedback} style={{ ...feedbackBtnStyle, borderColor: borderCol, color: textMuted }}><Smile size={16} /></button>
                                        <button onClick={handleFeedback} style={{ ...feedbackBtnStyle, borderColor: borderCol, color: textMuted }}><Meh size={16} /></button>
                                        <button onClick={handleFeedback} style={{ ...feedbackBtnStyle, borderColor: borderCol, color: textMuted }}><Frown size={16} /></button>
                                    </div>
                                )}
                            </div>
                        </div>

                    </div>
                </main>
            </div>

            {/* Custom Responsive CSS embedded */}
            <style dangerouslySetInnerHTML={{__html: `
                @media (max-width: 768px) {
                    .mobile-hamburger-btn {
                        display: flex !important;
                    }
                    .nav-desktop-links, .nav-search-bar {
                        display: none !important;
                    }
                    .docs-sidebar {
                        position: absolute !important;
                        top: 64px !important;
                        left: -280px !important;
                        height: calc(100vh - 64px) !important;
                        transition: left 0.3s ease !important;
                    }
                    .docs-sidebar.mobile-open {
                        left: 0 !important;
                    }
                    main {
                        padding: 16px !important;
                    }
                }
            `}} />
        </div>
    );
}

// Subcomponents
function AccordionCard({ id, title, isOpen, onToggle, theme, children }) {
    const isLight = theme === 'light';
    const bgHeader = isLight ? '#ffffff' : 'transparent';
    const bgExpanded = isLight ? '#f8fafc' : 'rgba(15, 23, 42, 0.2)';
    const textTitle = isLight ? '#1e293b' : '#e2e8f0';
    const borderCol = isLight ? '#e2e8f0' : 'rgba(255,255,255,0.05)';

    return (
        <div style={{
            backgroundColor: isLight ? '#ffffff' : 'rgba(30, 41, 59, 0.15)',
            border: `1px solid ${borderCol}`,
            borderRadius: '8px',
            overflow: 'hidden',
            boxShadow: isLight ? '0 1px 3px rgba(0,0,0,0.02)' : 'none',
            transition: 'background-color 0.2s, border-color 0.2s'
        }}>
            <div 
                onClick={onToggle}
                style={{
                    padding: '12px 16px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    cursor: 'pointer',
                    userSelect: 'none',
                    backgroundColor: isOpen ? (isLight ? '#f8fafc' : 'rgba(139, 92, 246, 0.05)') : bgHeader,
                    transition: 'background-color 0.2s'
                }}
            >
                <span style={{ fontSize: '14px', fontWeight: '700', color: textTitle }}>{title}</span>
                {isOpen ? <ChevronDown size={16} color="#7c3aed" /> : <ChevronRight size={16} color="#64748b" />}
            </div>
            {isOpen && (
                <div style={{
                    padding: '12px 16px',
                    borderTop: `1px solid ${borderCol}`,
                    backgroundColor: bgExpanded,
                    transition: 'background-color 0.2s'
                }}>
                    {children}
                </div>
            )}
        </div>
    );
}

// Inline Styles
const navHeaderLinkStyle = {
    backgroundColor: 'transparent',
    border: 'none',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    padding: '6px 10px',
    transition: 'color 0.2s'
};

const feedbackBtnStyle = {
    backgroundColor: 'transparent',
    borderRadius: '6px',
    width: '32px',
    height: '32px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    transition: 'all 0.2s'
};
