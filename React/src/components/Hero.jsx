import React, { useState, useEffect } from 'react';
import { Play, Zap, Layers, Cpu, FileText, Layout, Shield, CheckCircle2, ArrowRight, Terminal, Code, Database, FolderTree, Sparkles, ExternalLink } from 'lucide-react';

const PROJECTS = [
  {
    id: 'greenfield',
    icon: Zap,
    title: 'Greenfield',
    subtitle: 'Build from Zero',
    color: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
    description: 'Start fresh. AI generates complete architecture, schemas, and production-ready code.',
    brd: 'Build a subscription billing service with Stripe integration, JWT authentication, and PostgreSQL database. Include webhook handlers and Docker deployment.',
    techStack: { frontend: 'React + Vite', backend: 'Node.js + Express', database: 'PostgreSQL 15', orm: 'Prisma', auth: 'JWT', payments: 'Stripe SDK' },
    dbSchema: {
      tables: ['users', 'subscriptions', 'payments', 'webhooks', 'audit_logs'],
      relationships: 'users → subscriptions → payments, webhooks → payments'
    },
    compliance: [
      { name: 'Security Scan', status: 'PASS' },
      { name: 'Namespace Verification', status: 'PASS' },
      { name: 'Dependency Audit', status: 'PASS' },
      { name: 'Stripe API validation', status: 'PASS' }
    ],
    folders: [
      'controllers/ - Stripe API endpoints',
      'services/ - Webhook signature validation',
      'models/ - Schema models definition',
      'middleware/ - Auth & logging handler'
    ],
    terminalLogs: [
      { agent: '[agent_backend_05]', log: 'Initializing billing service...', state: 'info' },
      { agent: '[agent_backend_05]', log: '✓ Generated database tables schema', state: 'success' },
      { agent: '[agent_backend_12]', log: '✓ Implemented JWT authentication & routes', state: 'success' },
      { agent: '[agent_backend_08]', log: '✓ Created Stripe webhook handlers', state: 'success' },
      { agent: '[agent_devops_02]', log: '⟳ Configuring Docker container environment...', state: 'pending' },
      { agent: '[git]', log: '→ Pushed Stripe billing service to main branch', state: 'git' }
    ]
  },
  {
    id: 'brownfield',
    icon: Layers,
    title: 'Brownfield',
    subtitle: 'Enhance Existing',
    color: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
    description: 'Extend current systems. AI analyzes existing code and adds features without breaking changes.',
    brd: 'Add payment audit logging to existing billing-api repository. Create audit history table, log all webhook events, maintain backward compatibility.',
    techStack: { frontend: 'React', backend: 'Express + TypeScript', database: 'PostgreSQL', orm: 'TypeORM', auth: 'JWT' },
    dbSchema: {
      tables: ['audit_logs', 'payment_events'],
      relationships: 'audit_logs → users, payment_events → subscriptions'
    },
    compliance: [
      { name: 'Security Scan', status: 'PASS' },
      { name: 'Backward Compatibility', status: 'PASS' },
      { name: 'Dependency Audit', status: 'PASS' },
      { name: 'Regression Test Pass', status: 'PASS' }
    ],
    folders: [
      'controllers/audit/ - Payment logging routes',
      'services/logger/ - Audit event logger',
      'models/AuditLog/ - Schema adjustments',
      'middleware/ - Request inspection handler'
    ],
    terminalLogs: [
      { agent: '[agent_backend_03]', log: 'Indexing billing-api repository...', state: 'info' },
      { agent: '[agent_backend_03]', log: '✓ Analyzed legacy audit & webhook routes', state: 'success' },
      { agent: '[agent_backend_11]', log: '✓ Generated database schema extension', state: 'success' },
      { agent: '[agent_backend_12]', log: '✓ Injected payment logs hook automatically', state: 'success' },
      { agent: '[agent_devops_01]', log: '⟳ Running verification suite & tests...', state: 'pending' },
      { agent: '[git]', log: '→ Main branch updated with billing audit capability', state: 'git' }
    ]
  },
  {
    id: 'modernization',
    icon: Cpu,
    title: 'Modernization',
    subtitle: 'Transform Legacy',
    color: 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)',
    description: 'Migrate legacy systems. AI refactors outdated code to modern stacks while preserving logic.',
    brd: 'Migrate Python 2.7 + raw SQL to Node.js + Prisma ORM. Replace string interpolation queries with type-safe operations. Ensure 100% functional parity.',
    techStack: { frontend: 'React + TypeScript', backend: 'Node.js + Prisma', database: 'PostgreSQL', orm: 'Prisma', auth: 'Passport.js' },
    dbSchema: {
      tables: ['customers', 'orders', 'products', 'migrations'],
      relationships: 'customers → orders → products'
    },
    compliance: [
      { name: 'Legacy Parsing validation', status: 'PASS' },
      { name: 'Prisma SQL Injection Safe', status: 'PASS' },
      { name: 'Dependency Check', status: 'PASS' },
      { name: 'Functional Parity Check', status: 'PASS' }
    ],
    folders: [
      'controllers/api/ - Migrated routes',
      'prisma/schema/ - Generated schema',
      'services/ - Express controllers mapping',
      'routes/v1/ - API version 1 routers'
    ],
    terminalLogs: [
      { agent: '[agent_backend_07]', log: 'Scanning legacy Python 2.7 codebase...', state: 'info' },
      { agent: '[agent_backend_07]', log: '✓ Extracted raw SQL query strings', state: 'success' },
      { agent: '[agent_backend_15]', log: '✓ Ported logic to Node.js express routes', state: 'success' },
      { agent: '[agent_backend_15]', log: '✓ Compiled type-safe Prisma database bindings', state: 'success' },
      { agent: '[agent_devops_03]', log: '⟳ Running backward compatibility tests...', state: 'pending' },
      { agent: '[git]', log: '→ Migrated modern repository pushed to main branch', state: 'git' }
    ]
  }
];

const EXECUTION_MODES = [
  { id: 'developer_only', name: 'Dev Only', color: '#71717a', description: 'Manual coding', icon: Code },
  { id: 'ai_assist', name: 'AI Assist', color: '#06b6d4', description: 'VS Code suggestions', icon: Sparkles },
  { id: 'vibe_coding', name: 'Vibe Code', color: '#8b5cf6', description: 'Bourntec Platform', icon: Zap },
  { id: 'coexistence', name: 'Co-Exist', color: '#f59e0b', description: 'Human approval', icon: Shield },
  { id: 'ai_first', name: 'AI First', color: '#22c55e', description: 'Full autonomy', icon: Terminal }
];

const TABS = [
  { id: 'brd', label: 'Requirements', icon: FileText },
  { id: 'governance', label: 'Compliance', icon: Shield },
  { id: 'spec', label: 'Architecture', icon: Layout },
  { id: 'tasks', label: 'Task Backlog', icon: CheckCircle2 },
  { id: 'mode', label: 'Execution', icon: Terminal }
];

export default function Hero() {
  const [selectedProject, setSelectedProject] = useState('greenfield');
  const [consoleStep, setConsoleStep] = useState(0);
  const [isRunningConsole, setIsRunningConsole] = useState(true);
  const [scrollProgress, setScrollProgress] = useState(0);

  const project = PROJECTS.find(p => p.id === selectedProject);

  useEffect(() => {
    const handleScroll = () => {
      const scrolled = window.scrollY;
      const progress = Math.min(Math.max(scrolled / 450, 0), 1);
      setScrollProgress(progress);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll();
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    setConsoleStep(0);
    setIsRunningConsole(true);
  }, [selectedProject]);

  useEffect(() => {
    if (!isRunningConsole) return;
    const interval = setInterval(() => {
      setConsoleStep(prev => {
        if (prev < 5) {
          return prev + 1;
        } else {
          setIsRunningConsole(false);
          clearInterval(interval);
          return prev;
        }
      });
    }, 1500);
    return () => clearInterval(interval);
  }, [isRunningConsole, selectedProject]);

  const rotateX = 20 - scrollProgress * 20;
  const rotateY = -5 + scrollProgress * 5;
  const rotateZ = 1 - scrollProgress * 1;
  const scale = 0.92 + scrollProgress * 0.08;
  const translateY = 50 - scrollProgress * 50;

  const transformStyle = {
    transform: `perspective(1200px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) rotateZ(${rotateZ}deg) scale(${scale}) translateY(${translateY}px)`,
    transition: 'transform 0.1s cubic-bezier(0.25, 0.46, 0.45, 0.94)',
    transformStyle: 'preserve-3d',
    willChange: 'transform'
  };

  return (
    <section className="hero">
      <div className="hero-content">
        <div className="hero-badge">
          <Zap size={16} />
          <span>AI-Powered Development Platform</span>
        </div>

        <h1 className="hero-title">
          From Requirements to<br />
          <span className="gradient-text">Production Code</span>
        </h1>

        <p className="hero-description">
          DSuite transforms business requirements into production-ready applications. 
          AI agents analyze, design, validate, and build—while you maintain full control.
        </p>

        {/* Cortex-style 3-Column Interactive Workflow Wrapper with 3D Tilt */}
        <div className="cortex-workflow-wrapper" style={transformStyle}>
          <div className="cortex-glow-bg" />
          <div className="cortex-workflow-grid">
          
          {/* Card 01: Intake & Compliance */}
          <div className="cortex-card">
            <div className="card-step-badge step-1">01</div>
            <h3 className="card-step-title">Intake & Screening &rarr;</h3>
            <p className="card-step-desc">
              AI ingests requirements, screens dependencies, and verifies compliance gates.
            </p>
            
            {/* Interactive Section */}
            <div className="cortex-panel flex-col">
              {/* Project selector tabs */}
              <div style={{ display: 'flex', gap: 'var(--space-2)', width: '100%', marginBottom: 'var(--space-4)' }}>
                {PROJECTS.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setSelectedProject(p.id)}
                    className={`project-tab-btn ${selectedProject === p.id ? 'active' : ''}`}
                    style={{
                      flex: 1,
                      padding: 'var(--space-2) var(--space-1)',
                      fontSize: '0.75rem',
                      fontWeight: '700',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      border: '1px solid var(--border)',
                      background: selectedProject === p.id ? `${p.color}20` : 'var(--surface)',
                      color: selectedProject === p.id ? 'var(--text)' : 'var(--text-secondary)',
                      borderColor: selectedProject === p.id ? 'var(--primary)' : 'var(--border)',
                      transition: 'all 0.3s ease'
                    }}
                  >
                    {p.title}
                  </button>
                ))}
              </div>

              {/* Requirement Summary */}
              <div className="cortex-panel-sub-card" style={{ marginBottom: 'var(--space-4)', flexShrink: 0 }}>
                <div style={{ fontSize: '0.6875rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: '4px', fontWeight: 600 }}>
                  Requirements Ingest
                </div>
                <div style={{ fontSize: '0.8125rem', color: 'var(--text)', lineHeight: 1.4, textAlign: 'left' }}>
                  {project.description}
                </div>
              </div>

              {/* Compliance checklist */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', width: '100%' }}>
                <div style={{ fontSize: '0.6875rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: '2px', fontWeight: 600, textAlign: 'left' }}>
                  Compliance Gates
                </div>
                {project.compliance.map((item, idx) => (
                  <div key={idx} style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: 'var(--space-2) var(--space-3)',
                    background: 'var(--surface)',
                    borderRadius: '8px',
                    fontSize: '0.75rem',
                    border: '1px solid var(--border)'
                  }}>
                    <span style={{ color: 'var(--text-secondary)' }}>{item.name}</span>
                    <span style={{ color: 'var(--success)', fontWeight: 700, fontSize: '0.75rem' }}>✓ {item.status}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Card 02: Architecture Blueprinting */}
          <div className="cortex-card">
            <div className="card-step-badge step-2">02</div>
            <h3 className="card-step-title">Architectural Design &rarr;</h3>
            <p className="card-step-desc">
              Automatically designs schemas, structures folders, and generates database maps.
            </p>
            
            <div className="cortex-panel flex-col">
              {/* Tech Stack badging */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)', marginBottom: 'var(--space-4)' }}>
                {Object.entries(project.techStack).map(([key, value]) => (
                  <span key={key} className="badge badge-primary" style={{ fontSize: '0.625rem', padding: '3px 8px' }}>
                    {value}
                  </span>
                ))}
              </div>

              {/* Db Schema / Relational mapping */}
              <div className="cortex-panel-sub-card" style={{ marginBottom: 'var(--space-4)', width: '100%' }}>
                <div style={{ fontSize: '0.6875rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: '6px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }}>
                  <Database size={12} />
                  Database Schema
                </div>
                <div className="code-block" style={{ fontSize: '0.6875rem', padding: 'var(--space-2)', maxHeight: '100px', overflowY: 'auto', textAlign: 'left' }}>
                  <div style={{ color: 'var(--primary-light)', fontWeight: 600 }}>Tables:</div>
                  {project.dbSchema.tables.map((table, i) => (
                    <div key={i} style={{ paddingLeft: '6px', margin: '2px 0' }}>• {table}</div>
                  ))}
                  <div style={{ color: 'var(--primary-light)', fontWeight: 600, marginTop: '6px' }}>Relationships:</div>
                  <div>{project.dbSchema.relationships}</div>
                </div>
              </div>

              {/* Folder tree structure preview */}
              <div className="cortex-panel-sub-card" style={{ width: '100%' }}>
                <div style={{ fontSize: '0.6875rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: '6px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }}>
                  <FolderTree size={12} />
                  Folder Blueprint
                </div>
                <div className="code-block" style={{ fontSize: '0.6875rem', padding: 'var(--space-2)', fontFamily: 'var(--font-mono)', textAlign: 'left' }}>
                  <span style={{ color: '#10b981' }}>src/</span><br/>
                  {project.folders.map((f, idx) => (
                    <div key={idx} style={{ paddingLeft: '8px' }}>
                      ├── <span style={{ color: '#818cf8' }}>{f.split(' - ')[0]}</span> - {f.split(' - ')[1]}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Card 03: Autonomous Build */}
          <div className="cortex-card">
            <div className="card-step-badge step-3">03</div>
            <h3 className="card-step-title">Autonomous Build &rarr;</h3>
            <p className="card-step-desc">
              Pools parallel agents, locks critical assets, and commits production builds.
            </p>
            
            <div className="cortex-panel flex-col">
              {/* Agent pool metrics */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)', width: '100%', marginBottom: 'var(--space-4)' }}>
                <div style={{ padding: 'var(--space-2)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.625rem', color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
                    Active Pool
                  </div>
                  <div style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--primary-light)' }}>
                    30 Agents
                  </div>
                </div>
                <div style={{ padding: 'var(--space-2)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.625rem', color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
                    Agent Lock
                  </div>
                  <div style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--success)' }}>
                    Active
                  </div>
                </div>
              </div>

              {/* Scrolling Console log simulation */}
              <div className="cortex-terminal-wrapper" style={{
                background: '#0d0d12',
                border: '1px solid var(--border)',
                borderRadius: '12px',
                width: '100%',
                overflow: 'hidden',
                flex: 1,
                display: 'flex',
                flexDirection: 'column'
              }}>
                <div style={{
                  padding: '6px 12px',
                  background: 'rgba(17, 17, 24, 0.8)',
                  borderBottom: '1px solid var(--border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexShrink: 0
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Terminal size={12} color="var(--primary-light)" />
                    <span style={{ fontSize: '0.6875rem', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', fontWeight: 600 }}>
                      Agent Terminal
                    </span>
                  </div>
                  <span className={isRunningConsole ? "status-dot" : ""} style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    background: isRunningConsole ? 'var(--success)' : 'var(--text-tertiary)',
                    animation: isRunningConsole ? 'pulse-dot 2s ease-in-out infinite' : 'none'
                  }} />
                </div>
                
                <div style={{
                  padding: 'var(--space-3)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.6875rem',
                  lineHeight: 1.6,
                  textAlign: 'left',
                  overflowY: 'auto',
                  flex: 1,
                  minHeight: '170px'
                }}>
                  {project.terminalLogs.slice(0, consoleStep + 1).map((log, idx) => (
                    <div
                      key={idx}
                      style={{
                        marginBottom: '4px',
                        color: log.state === 'success' ? '#10b981' : log.state === 'pending' ? '#22d3ee' : log.state === 'git' ? '#a78bfa' : 'var(--text-secondary)',
                        animation: 'slide-in 0.3s ease-out'
                      }}
                    >
                      <span style={{ color: 'var(--primary-light)' }}>{log.agent}</span> {log.log}
                    </div>
                  ))}
                  
                  {/* Cursor blink */}
                  {isRunningConsole && (
                    <span style={{
                      display: 'inline-block',
                      width: '6px',
                      height: '12px',
                      background: 'var(--primary)',
                      marginLeft: '2px',
                      animation: 'pulse-dot 1s ease-in-out infinite',
                      verticalAlign: 'middle'
                    }} />
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
  );
}
