import React, { useState, useEffect, useRef } from 'react';
import { Play, Pause, UploadCloud, CheckCircle2, Database, Terminal, ExternalLink, FileText, CheckSquare, Layers, Cpu, Code2, ArrowRight } from 'lucide-react';

const TOUR_STEPS = [
  {
    id: 0,
    title: '01. Ingest Requirements',
    subtitle: 'Upload & Compliance check',
    description: 'AI ingests your PDF/text Business Requirement Document (BRD), checks organizational namespace, runs regression tests, and flags API compliance gates.',
    icon: FileText
  },
  {
    id: 1,
    title: '02. Codebase Architecture',
    subtitle: 'System layout & schemas',
    description: 'AI constructs the repository architecture, defines the folder layout, configures target languages (TypeScript, Node), and maps database tables and relational keys.',
    icon: Database
  },
  {
    id: 2,
    title: '03. Task Decomposition',
    subtitle: 'Backlog & effort estimation',
    description: 'AI splits the blueprint requirements into sequenced tasks, lists descriptions, determines file dependencies, and sets precise effort estimates.',
    icon: CheckSquare
  },
  {
    id: 3,
    title: '04. Multi-Agent Swarm',
    subtitle: 'Simultaneous execution logs',
    description: 'Specialized backend, UI, and DevOps agents acquire file locks, set sandbox containers, compile endpoints, and pass unit tests concurrently.',
    icon: Terminal
  },
  {
    id: 4,
    title: '05. Git Push & Live Deploy',
    subtitle: 'Commit, merge & sandbox launch',
    description: 'DSuite runs final system integrations, pushes a clean commit to your main branch, merges code, and deploys the application sandbox live.',
    icon: ExternalLink
  }
];

const CODE_FILES = {
  'schema.prisma': `datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model ConversionConfig {
  id                    Int      @id @default(autoincrement())
  mode                  String
  threshold             Float
  enableBigInt          Boolean
  enableStringFallback  Boolean
  defaultFormat         String
}

model DatabaseSchema {
  id                  Int      @id @default(autoincrement())
  tableName           String
  columnName          String
  dataType            String
  requiresSafeHandling Boolean
  maxValue            Float
}

model SafeInteger {
  id            Int      @id @default(autoincrement())
  value         String
  type          String
  isLarge       Boolean
  originalValue String
  precision     Float
}

model OperationResult {
  id        Int      @id @default(autoincrement())
  status    String
  resultId  Int
  result    SafeInteger @relation(fields: [resultId], references: [id])
  error     String?
  timestamp BigInt
  operation String
}`,
  'gateway.js': `const express = require('express');
const { processIntegerSafety } = require('../services/safety-layer');
const router = express.Router();

// Turso Query Gateway Endpoint
router.post('/query', async (req, res) => {
  const { query } = req.body;
  try {
    const rawResult = await db.execute(query);
    const safeResult = rawResult.rows.map(row => {
      return processIntegerSafety(row.val, row.type);
    });
    res.json({
      status: 'success',
      result: safeResult,
      error: null,
      timestamp: Date.now(),
      operation: 'SELECT'
    });
  } catch (err) {
    res.status(500).json({ status: 'error', error: err.message });
  }
});

module.exports = router;`,
  'safety-layer.js': `const MAX_SAFE = Number.MAX_SAFE_INTEGER; // 9007199254740991

// Integer Safety Layer middleware
function processIntegerSafety(value, dataType) {
  if (typeof value === 'number' || dataType === 'number') {
    if (value > MAX_SAFE) {
      // Convert to string to avoid precision loss
      return {
        value: value.toString(),
        type: 'string',
        isLarge: true,
        originalValue: value,
        precision: 64
      };
    }
  }
  return {
    value: value,
    type: 'number',
    isLarge: false,
    originalValue: value,
    precision: 32
  };
}

module.exports = { processIntegerSafety };`
};

const SHOWCASE_TASKS = [
  {
    id: 'stripe',
    title: 'Turso Gateway Interceptor',
    badge: 'TS-102 Interceptor',
    desc: 'Express query safety interceptor querying Turso DB and formatting numeric outputs.',
    file: 'gateway.js',
    log: '[System] Booting Turso safety gateway...\n[Express] Route initialized: /api/query\n[SafetyLayer] Intercepting Turso query response stream...'
  },
  {
    id: 'schema',
    title: 'Database Schema Specs',
    badge: 'TS-101 Specs',
    desc: 'Prisma ORM models mapping ConversionConfig, DatabaseSchema, and SafeInteger tables.',
    file: 'schema.prisma',
    log: '[Prisma] Generating client...\n[Prisma] Table ConversionConfig & DatabaseSchema compiled.\n[Prisma] ✓ Relational database schema applied successfully.'
  },
  {
    id: 'billing',
    title: 'Integer Safety Middleware',
    badge: 'TS-103 Middleware',
    desc: 'Safety validator converting numbers greater than MAX_SAFE_INTEGER to strings.',
    file: 'safety-layer.js',
    log: '[Express] Express safety middleware active on /query\n[SafetyLayer] Found integer 9007199254740992 > MAX_SAFE_INTEGER. Converting to string.\n[System] Response serialized safely.'
  }
];

export default function TourPlayer() {
  const [activeStep, setActiveStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [taskAnimationStep, setTaskAnimationStep] = useState(0);
  const [showSandboxApp, setShowSandboxApp] = useState(false);
  const [activeBoardTab, setActiveBoardTab] = useState('board');
  const [selectedFile, setSelectedFile] = useState('gateway.js');
  const [agentProgress, setAgentProgress] = useState({ ui: 0, backend: 0, devops: 0 });
  const [showcaseTaskIndex, setShowcaseTaskIndex] = useState(0);
  const [isAppLaunched, setIsAppLaunched] = useState(false);
  const timerRef = useRef(null);

  // Auto-play steps logic
  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);

    if (isPlaying) {
      timerRef.current = setInterval(() => {
        setActiveStep(prev => (prev < TOUR_STEPS.length - 1 ? prev + 1 : 0));
      }, 5500);
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying]);

  // Reset local step animations on active step change
  useEffect(() => {
    if (activeStep === 0) {
      setUploadProgress(0);
      const interval = setInterval(() => {
        setUploadProgress(prev => {
          if (prev < 100) return prev + 5;
          clearInterval(interval);
          return 100;
        });
      }, 80);
      return () => clearInterval(interval);
    } else if (activeStep === 2) {
      setTaskAnimationStep(0);
      const interval = setInterval(() => {
        setTaskAnimationStep(prev => {
          if (prev < 5) return prev + 1;
          clearInterval(interval);
          return 5;
        });
      }, 600);
      return () => clearInterval(interval);
    } else if (activeStep === 3) {
      setAgentProgress({ ui: 0, backend: 0, devops: 0 });
      const interval = setInterval(() => {
        setAgentProgress(prev => {
          const nextUi = Math.min(prev.ui + Math.floor(Math.random() * 12) + 6, 100);
          const nextBackend = Math.min(prev.backend + Math.floor(Math.random() * 16) + 8, 100);
          const nextDevops = Math.min(prev.devops + Math.floor(Math.random() * 8) + 4, 100);
          
          if (nextUi === 100 && nextBackend === 100 && nextDevops === 100) {
            clearInterval(interval);
          }
          
          return { ui: nextUi, backend: nextBackend, devops: nextDevops };
        });
      }, 250);
      return () => clearInterval(interval);
    } else if (activeStep === 4) {
      setIsAppLaunched(false);
      const timeout = setTimeout(() => {
        setIsAppLaunched(true);
      }, 2200);
      return () => clearTimeout(timeout);
    }
  }, [activeStep]);

  const handleStepSelect = (stepId) => {
    setActiveStep(stepId);
    setIsPlaying(false); // Pause auto-play when user manually interacts
  };

  const renderIngest = () => {
    const isDone = uploadProgress === 100;
    return (
      <div className="tour-content-panel flex-col" style={{ gap: 'var(--space-4)' }}>
        <div className="dropzone-mock">
          <UploadCloud size={32} className="accent-violet-glow" style={{ color: 'var(--primary-light)', marginBottom: '8px' }} />
          <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>safe_integer_turso_gateway.pdf</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>File Size: 1.8 MB</div>
          
          <div className="progress-bar-container" style={{ width: '80%', height: '4px', background: 'var(--bg)', borderRadius: '2px', marginTop: '12px', overflow: 'hidden' }}>
            <div style={{ height: '100%', background: 'var(--gradient-primary)', width: `${uploadProgress}%`, transition: 'width 0.1s ease' }}></div>
          </div>
          <div style={{ fontSize: '0.6875rem', marginTop: '4px', fontFamily: 'var(--font-mono)', color: 'var(--primary-light)' }}>
            {isDone ? 'Ingest Completed 100%' : `Uploading: ${uploadProgress}%`}
          </div>
        </div>

        {isDone && (
          <div className="reveal-on-scroll reveal-visible" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 700, letterSpacing: '0.05em', textAlign: 'left' }}>
              Compliance Checklist
            </div>
            {[
              { name: 'MAX_SAFE_INTEGER Check', desc: 'Flag large integers' },
              { name: 'Turso Schema Integrity Check', desc: 'Verify numeric columns' },
              { name: 'Drizzle Driver Audit', desc: 'Security gate check' }
            ].map((gate, i) => (
              <div key={i} className="checklist-item-mock">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <CheckCircle2 size={14} color="var(--success)" />
                  <span style={{ fontWeight: 600 }}>{gate.name}</span>
                </div>
                <span className="badge badge-success" style={{ fontSize: '0.625rem' }}>Pass</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderBlueprint = () => (
    <div className="tour-content-panel flex-col" style={{ gap: 'var(--space-4)' }}>
      <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        {['TypeScript', 'Node.js', 'Prisma ORM', 'Turso DB', 'Drizzle ORM'].map((tech, i) => (
          <span key={i} className="badge badge-primary" style={{ fontSize: '0.6875rem', textTransform: 'none' }}>{tech}</span>
        ))}
      </div>

      {/* Generated Diagrams from DSuite */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)', flex: 1 }}>
        {/* Workflow Flowchart */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderRight: '1px solid rgba(255, 255, 255, 0.08)', paddingRight: '12px' }}>
          <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: '2px', textAlign: 'left', letterSpacing: '0.05em' }}>
            Workflow Flowchart
          </div>
          <div style={{ 
            background: 'rgba(9, 9, 11, 0.6)', 
            borderRadius: '12px', 
            padding: '16px',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            overflow: 'auto',
            maxHeight: '280px',
            backdropFilter: 'blur(8px)'
          }}>
            <svg viewBox="0 0 300 400" style={{ width: '100%', height: 'auto', display: 'block' }}>
              <defs>
                <filter id="glow-line-filter" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="2" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
                <linearGradient id="indigoGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="rgba(129, 140, 248, 0.2)" />
                  <stop offset="100%" stopColor="rgba(99, 102, 241, 0.2)" />
                </linearGradient>
                <linearGradient id="amberGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="rgba(251, 191, 36, 0.15)" />
                  <stop offset="100%" stopColor="rgba(245, 158, 11, 0.15)" />
                </linearGradient>
                <linearGradient id="emeraldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="rgba(52, 211, 153, 0.15)" />
                  <stop offset="100%" stopColor="rgba(16, 185, 129, 0.15)" />
                </linearGradient>
                <marker id="arrowhead" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                  <polygon points="0 0, 7 3, 0 6" fill="#475569"/>
                </marker>
                <marker id="arrowhead-highlight" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                  <polygon points="0 0, 7 3, 0 6" fill="#818cf8"/>
                </marker>
              </defs>

              {/* Developer Node */}
              <rect x="110" y="5" width="80" height="30" fill="url(#indigoGrad)" stroke="#818cf8" strokeWidth="1.5" rx="6" filter="url(#glow-line-filter)"/>
              <text x="150" y="23" textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fontWeight="600" fill="#f8fafc">Developer</text>
              
              {/* Arrow down */}
              <path d="M 150 35 L 150 55" stroke="#475569" strokeWidth="1.2" fill="none" markerEnd="url(#arrowhead)"/>
              <text x="155" y="47" fontSize="7" fontFamily="var(--font-body)" fill="#94a3b8">Performs Operations</text>
              
              {/* Application Logic */}
              <rect x="70" y="55" width="160" height="30" fill="url(#indigoGrad)" stroke="#6366f1" strokeWidth="1.5" rx="6"/>
              <text x="150" y="73" textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fontWeight="600" fill="#f8fafc">Application Logic</text>
              
              {/* Arrow down */}
              <path d="M 150 85 L 150 105" stroke="#475569" strokeWidth="1.2" fill="none" markerEnd="url(#arrowhead)"/>
              <text x="155" y="97" fontSize="7" fontFamily="var(--font-body)" fill="#94a3b8">Uses Conversion Utils</text>
              
              {/* BigInt/String Operations */}
              <rect x="55" y="105" width="190" height="30" fill="url(#indigoGrad)" stroke="#818cf8" strokeWidth="1.5" rx="6"/>
              <text x="150" y="123" textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fontWeight="600" fill="#f8fafc">BigInt/String Operations</text>
              
              {/* Arrow down */}
              <path d="M 150 135 L 150 155" stroke="#475569" strokeWidth="1.2" fill="none" markerEnd="url(#arrowhead)"/>
              <text x="155" y="147" fontSize="7" fontFamily="var(--font-body)" fill="#94a3b8">Safe Arithmetic</text>
              
              {/* Valid Results */}
              <rect x="30" y="155" width="90" height="30" fill="rgba(59, 130, 246, 0.1)" stroke="#3b82f6" strokeWidth="1.2" rx="6"/>
              <text x="75" y="173" textAnchor="middle" fontSize="9" fontFamily="var(--font-mono)" fontWeight="600" fill="#93c5fd">Valid Results</text>
              
              {/* Drizzle Studio */}
              <rect x="180" y="155" width="90" height="30" fill="url(#indigoGrad)" stroke="#6366f1" strokeWidth="1.2" rx="6"/>
              <text x="225" y="173" textAnchor="middle" fontSize="9" fontFamily="var(--font-mono)" fontWeight="600" fill="#c7d2fe">Drizzle Studio</text>
              
              {/* Arrows converge to Integer Safety Layer */}
              <path d="M 75 185 L 75 210 L 150 210 L 150 225" stroke="#475569" strokeWidth="1.2" fill="none" markerEnd="url(#arrowhead)"/>
              <path d="M 225 185 L 225 210 L 150 210" stroke="#475569" strokeWidth="1.2" fill="none"/>
              
              {/* Integer Safety Layer */}
              <rect x="55" y="225" width="190" height="30" fill="url(#amberGrad)" stroke="#f59e0b" strokeWidth="1.5" rx="6" filter="url(#glow-line-filter)"/>
              <text x="150" y="243" textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fontWeight="700" fill="#fbbf24">Integer Safety Layer</text>
              
              {/* Arrow down */}
              <path d="M 150 255 L 150 275" stroke="#475569" strokeWidth="1.2" fill="none" markerEnd="url(#arrowhead)"/>
              <text x="155" y="267" fontSize="7" fontFamily="var(--font-body)" fill="#94a3b8">Detect Large Integers</text>
              
              {/* Decision Diamond */}
              <path d="M 150 275 L 210 310 L 150 345 L 90 310 Z" fill="url(#indigoGrad)" stroke="#818cf8" strokeWidth="1.5"/>
              <text x="150" y="306" textAnchor="middle" fontSize="8" fontFamily="var(--font-mono)" fontWeight="700" fill="#f8fafc">Integer &gt;</text>
              <text x="150" y="318" textAnchor="middle" fontSize="8" fontFamily="var(--font-mono)" fontWeight="700" fill="#f8fafc">MAX_SAFE_INTEGER?</text>
              
              {/* Yes path */}
              <path d="M 90 310 L 30 310 L 30 370" stroke="#10b981" strokeWidth="1.2" fill="none" markerEnd="url(#arrowhead-highlight)" filter="url(#glow-line-filter)"/>
              <text x="35" y="305" fontSize="8" fontFamily="var(--font-mono)" fill="#10b981" fontWeight="700">Yes</text>
              
              {/* No path */}
              <path d="M 210 310 L 270 310 L 270 370" stroke="#ef4444" strokeWidth="1.2" fill="none" markerEnd="url(#arrowhead)"/>
              <text x="245" y="305" fontSize="8" fontFamily="var(--font-mono)" fill="#ef4444" fontWeight="700">No</text>
              
              {/* Convert to BigInt/String */}
              <rect x="5" y="370" width="55" height="25" fill="url(#emeraldGrad)" stroke="#10b981" strokeWidth="1.5" rx="4"/>
              <text x="32.5" y="381" textAnchor="middle" fontSize="7" fontFamily="var(--font-mono)" fontWeight="700" fill="#a7f3d0">Convert to</text>
              <text x="32.5" y="390" textAnchor="middle" fontSize="7" fontFamily="var(--font-mono)" fontWeight="700" fill="#a7f3d0">BigInt/String</text>
              
              {/* Pass Through as Number */}
              <rect x="240" y="370" width="55" height="25" fill="rgba(239, 68, 68, 0.08)" stroke="#ef4444" strokeWidth="1.2" rx="4"/>
              <text x="267.5" y="381" textAnchor="middle" fontSize="7" fontFamily="var(--font-mono)" fontWeight="700" fill="#fca5a5">Pass Through</text>
              <text x="267.5" y="390" textAnchor="middle" fontSize="7" fontFamily="var(--font-mono)" fontWeight="700" fill="#fca5a5">as Number</text>
            </svg>
          </div>
        </div>

        {/* Database Schema UML */}
        <div>
          <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: '6px', textAlign: 'left', letterSpacing: '0.05em' }}>
            Database Schema UML
          </div>
          <div style={{ 
            background: 'rgba(9, 9, 11, 0.6)', 
            borderRadius: '12px', 
            padding: '16px',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            overflow: 'auto',
            maxHeight: '280px',
            backdropFilter: 'blur(8px)'
          }}>
            <svg viewBox="0 0 320 380" style={{ width: '100%', height: 'auto', display: 'block' }}>
              {/* ConversionConfig Entity */}
              <g>
                <rect x="10" y="10" width="140" height="25" fill="rgba(139, 92, 246, 0.15)" stroke="#a855f7" strokeWidth="1.5" rx="4"/>
                <text x="80" y="26" textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fontWeight="700" fill="#c084fc">ConversionConfig</text>
                
                <rect x="10" y="35" width="70" height="80" fill="rgba(255, 255, 255, 0.02)" stroke="rgba(168, 85, 247, 0.3)" strokeWidth="1"/>
                <text x="15" y="48" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">string</text>
                <text x="15" y="60" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">number</text>
                <text x="15" y="72" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">boolean</text>
                <text x="15" y="84" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">boolean</text>
                <text x="15" y="96" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">string</text>
                
                <rect x="80" y="35" width="70" height="80" fill="rgba(255, 255, 255, 0.02)" stroke="rgba(168, 85, 247, 0.3)" strokeWidth="1"/>
                <text x="85" y="48" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">mode</text>
                <text x="85" y="60" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">threshold</text>
                <text x="85" y="72" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">enableBigInt</text>
                <text x="85" y="84" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">enableStrFallback</text>
                <text x="85" y="96" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">defaultFormat</text>
              </g>

              {/* DatabaseSchema Entity */}
              <g>
                <rect x="170" y="10" width="140" height="25" fill="rgba(139, 92, 246, 0.15)" stroke="#a855f7" strokeWidth="1.5" rx="4"/>
                <text x="240" y="26" textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fontWeight="700" fill="#c084fc">DatabaseSchema</text>
                
                <rect x="170" y="35" width="70" height="80" fill="rgba(255, 255, 255, 0.02)" stroke="rgba(168, 85, 247, 0.3)" strokeWidth="1"/>
                <text x="175" y="48" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">string</text>
                <text x="175" y="60" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">string</text>
                <text x="175" y="72" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">string</text>
                <text x="175" y="84" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">boolean</text>
                <text x="175" y="96" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">number</text>
                
                <rect x="240" y="35" width="70" height="80" fill="rgba(255, 255, 255, 0.02)" stroke="rgba(168, 85, 247, 0.3)" strokeWidth="1"/>
                <text x="245" y="48" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">tableName</text>
                <text x="245" y="60" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">columnName</text>
                <text x="245" y="72" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">dataType</text>
                <text x="245" y="84" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">safeHandling</text>
                <text x="245" y="96" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">maxValue</text>
              </g>

              {/* Connection lines from top entities to SafeInteger */}
              <path d="M 80 115 L 80 135 L 160 135 L 160 155" stroke="#a855f7" strokeWidth="1.2" fill="none"/>
              <text x="85" y="130" fontSize="7" fontFamily="var(--font-body)" fill="#c084fc">configures</text>
              
              <path d="M 240 115 L 240 135 L 160 135" stroke="#a855f7" strokeWidth="1.2" fill="none"/>
              <text x="185" y="130" fontSize="7" fontFamily="var(--font-body)" fill="#c084fc">contains</text>

              {/* SafeInteger Entity (Central) */}
              <g>
                <rect x="90" y="155" width="140" height="25" fill="rgba(139, 92, 246, 0.15)" stroke="#a855f7" strokeWidth="1.5" rx="4"/>
                <text x="160" y="171" textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fontWeight="700" fill="#c084fc">SafeInteger</text>
                
                <rect x="90" y="180" width="70" height="80" fill="rgba(255, 255, 255, 0.02)" stroke="rgba(168, 85, 247, 0.3)" strokeWidth="1"/>
                <text x="95" y="193" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">string</text>
                <text x="95" y="205" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">string</text>
                <text x="95" y="217" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">boolean</text>
                <text x="95" y="229" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">string</text>
                <text x="95" y="241" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">number</text>
                
                <rect x="160" y="180" width="70" height="80" fill="rgba(255, 255, 255, 0.02)" stroke="rgba(168, 85, 247, 0.3)" strokeWidth="1"/>
                <text x="165" y="193" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">value</text>
                <text x="165" y="205" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">type</text>
                <text x="165" y="217" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">isLarge</text>
                <text x="165" y="229" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">originalVal</text>
                <text x="165" y="241" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">precision</text>
              </g>

              {/* Connection line from SafeInteger to OperationResult */}
              <path d="M 160 260 L 160 280" stroke="#a855f7" strokeWidth="1.2" fill="none" markerEnd="url(#uml-arrow)"/>
              <text x="165" y="273" fontSize="7" fontFamily="var(--font-body)" fill="#c084fc">produces</text>
              
              {/* Cardinality symbols */}
              <circle cx="160" cy="268" r="2.5" fill="#09090b" stroke="#a855f7" strokeWidth="1"/>
              <circle cx="160" cy="282" r="2.5" fill="#09090b" stroke="#a855f7" strokeWidth="1"/>

              {/* OperationResult Entity */}
              <g>
                <rect x="90" y="290" width="140" height="25" fill="rgba(139, 92, 246, 0.15)" stroke="#a855f7" strokeWidth="1.5" rx="4"/>
                <text x="160" y="306" textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fontWeight="700" fill="#c084fc">OperationResult</text>
                
                <rect x="90" y="315" width="70" height="72" fill="rgba(255, 255, 255, 0.02)" stroke="rgba(168, 85, 247, 0.3)" strokeWidth="1"/>
                <text x="95" y="328" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">string</text>
                <text x="95" y="340" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">SafeInteger</text>
                <text x="95" y="352" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">string</text>
                <text x="95" y="364" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">number</text>
                <text x="95" y="376" fontSize="8" fontFamily="var(--font-mono)" fill="#94a3b8">string</text>
                
                <rect x="160" y="315" width="70" height="72" fill="rgba(255, 255, 255, 0.02)" stroke="rgba(168, 85, 247, 0.3)" strokeWidth="1"/>
                <text x="165" y="328" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">status</text>
                <text x="165" y="340" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">result</text>
                <text x="165" y="352" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">error</text>
                <text x="165" y="364" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">timestamp</text>
                <text x="165" y="376" fontSize="8" fontFamily="var(--font-mono)" fill="#e2e8f0">operation</text>
              </g>

              {/* UML Arrow marker */}
              <defs>
                <marker id="uml-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                  <polygon points="0 0, 7 3, 0 6" fill="#09090b" stroke="#a855f7" strokeWidth="1"/>
                </marker>
              </defs>
            </svg>
          </div>
        </div>
      </div>

      <div style={{ 
        fontSize: '0.75rem', 
        color: 'var(--text-tertiary)', 
        textAlign: 'center',
        fontStyle: 'italic',
        padding: 'var(--space-2)',
        background: 'rgba(139, 92, 246, 0.04)',
        borderRadius: '6px',
        border: '1px solid rgba(139, 92, 246, 0.12)'
      }}>
        ✨ Auto-generated diagrams from DSuite analysis engine
      </div>
    </div>
  );

  const renderTasks = () => {
    const tasks = [
      { id: 'TS-101', name: 'Configure ConversionConfig & DatabaseSchema relational tables in schema.prisma', effort: '2h', status: 'done' },
      { id: 'TS-102', name: 'Develop Integer Safety Layer middleware for Turso driver', effort: '3h', status: 'done' },
      { id: 'TS-103', name: 'Code response formatter serializer for Drizzle Studio query outputs', effort: '4h', status: 'done' },
      { id: 'TS-104', name: 'Setup Turso DB container & Drizzle local migration scripts', effort: '2h', status: 'running' },
      { id: 'TS-105', name: 'Write mocha integration suites for safe integer conversion checks', effort: '3h', status: 'pending' }
    ];

    return (
      <div className="tour-content-panel flex-col" style={{ gap: 'var(--space-3)' }}>
        <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: '2px', textAlign: 'left' }}>
          Decomposed Backlog Items
        </div>
        {tasks.map((task, i) => {
          const isVisible = taskAnimationStep >= i;
          return (
            <div
              key={i}
              className={`checklist-item-mock ${isVisible ? 'reveal-visible' : ''}`}
              style={{
                opacity: isVisible ? 1 : 0,
                transform: isVisible ? 'translateY(0)' : 'translateY(10px)',
                transition: 'all 0.3s ease',
                background: task.status === 'running' ? 'rgba(6, 182, 212, 0.08)' : 'var(--surface)',
                borderColor: task.status === 'running' ? 'var(--secondary)' : 'var(--border)'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {task.status === 'done' ? (
                  <CheckCircle2 size={16} color="var(--success)" />
                ) : task.status === 'running' ? (
                  <span className="status-dot" style={{ width: '8px', height: '8px', background: 'var(--secondary)' }}></span>
                ) : (
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--border-light)' }}></span>
                )}
                <div>
                  <span style={{ fontWeight: 700, fontSize: '0.75rem', color: 'var(--text-tertiary)', marginRight: '6px' }}>{task.id}</span>
                  <span style={{ fontWeight: 600, fontSize: '0.8125rem' }}>{task.name}</span>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', color: 'var(--text-tertiary)' }}>{task.effort}</span>
                <span className={`badge ${task.status === 'done' ? 'badge-success' : task.status === 'running' ? 'badge-primary' : 'badge-warning'}`} style={{ fontSize: '0.5625rem', padding: '2px 6px' }}>
                  {task.status}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderExecution = () => {
    const agents = [
      { id: 'backend', name: 'agent_backend_15', role: 'Backend API Developer', task: 'TS-102: Gateway safety middleware & interceptor', progress: agentProgress.backend, color: 'var(--primary-light)' },
      { id: 'ui', name: 'agent_ui_08', role: 'UI Components Designer', task: 'TS-103: Response formatter serializer adapter', progress: agentProgress.ui, color: 'var(--secondary)' },
      { id: 'devops', name: 'agent_devops_03', role: 'DevOps Systems Engineer', task: 'TS-104: Turso DB container & Drizzle migration scripts', progress: agentProgress.devops, color: 'var(--success)' }
    ];

    return (
      <div className="tour-content-panel flex-col" style={{ gap: 'var(--space-3)' }}>
        <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: '2px', textAlign: 'left' }}>
          Simultaneous Agent Execution Progress
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {agents.map((agent) => (
            <div 
              key={agent.id} 
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'stretch',
                padding: '12px 14px',
                gap: '8px',
                background: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid var(--border)',
                borderRadius: '12px',
                transition: 'all 0.3s ease'
              }}
              className="cortex-agent-progress-card"
            >
              {/* Row 1: Agent name & Completed status */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div className="status-dot" style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    background: agent.progress === 100 ? 'var(--success)' : agent.color,
                    animation: agent.progress === 100 ? 'none' : 'pulse-dot 1.5s ease-in-out infinite'
                  }}></div>
                  <span style={{ fontWeight: 700, fontSize: '0.75rem', color: agent.color, fontFamily: 'var(--font-mono)' }}>{agent.name}</span>
                </div>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 700, color: agent.progress === 100 ? 'var(--success)' : 'var(--text-secondary)' }}>
                  {agent.progress === 100 ? '✓ Completed' : `${agent.progress}%`}
                </span>
              </div>
              
              {/* Row 2: Assigned task description */}
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textAlign: 'left', fontWeight: 500 }}>
                Active: {agent.task}
              </div>
              
              {/* Row 3: Progress bar line */}
              <div style={{ width: '100%', height: '4px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '2px', overflow: 'hidden' }}>
                <div style={{
                  height: '100%',
                  background: agent.progress === 100 ? 'var(--success)' : `linear-gradient(90deg, ${agent.color} 0%, var(--primary) 100%)`,
                  width: `${agent.progress}%`,
                  transition: 'width 0.25s ease'
                }}></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderDeployment = () => {
    return (
      <div className="tour-content-panel flex-col" style={{ gap: 'var(--space-4)', justifyContent: 'center' }}>
        <div style={{ background: '#09090d', border: '1px solid var(--border)', borderRadius: '10px', padding: '12px', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', lineHeight: 1.6, textAlign: 'left' }}>
          <div>$ git add . &amp;&amp; git commit -m "feat: implement Turso safe-integer conversion gateway"</div>
          <div style={{ color: 'var(--text-tertiary)' }}>[main 9b8a2c] feat: implement Turso safe-integer conversion gateway</div>
          <div>$ git push origin main</div>
          <div style={{ color: 'var(--primary-light)' }}>Pushing code to GitHub repository...</div>
          <div style={{ color: 'var(--success)' }}>✓ Codebase successfully synced with git/main</div>
          <div style={{ color: 'var(--success)' }}>🚀 Safety Gateway compiled and hosted live.</div>
        </div>

        <div style={{ textAlign: 'center' }}>
          <button 
            className="btn btn-primary"
            onClick={() => {
              setIsAppLaunched(true);
              setIsPlaying(false);
            }}
            style={{ padding: 'var(--space-3) var(--space-6)', fontSize: '0.8125rem', gap: '6px' }}
          >
            Launch Compiled Application
            <ExternalLink size={14} />
          </button>
        </div>
      </div>
    );
  };

  const renderBourntecLanding = () => {
    return (
      <div className="bourntec-landing" style={{ margin: '-20px', padding: '0px' }}>
        <nav className="bourntec-nav" style={{ padding: '8px 16px', top: 0 }}>
          <div className="bourntec-nav-logo" style={{ fontSize: '0.875rem' }}>
            BOURNTEC SUITE
          </div>
          <div className="bourntec-nav-links" style={{ gap: '12px' }}>
            <a href="#features" className="bourntec-nav-link" style={{ fontSize: '0.6875rem' }}>Features</a>
            <a href="#showcase" className="bourntec-nav-link" style={{ fontSize: '0.6875rem' }}>Sandbox</a>
            <a href="#telemetry" className="bourntec-nav-link" style={{ fontSize: '0.6875rem' }}>Telemetry</a>
          </div>
          <button 
            onClick={() => setIsAppLaunched(false)}
            style={{
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              color: 'var(--text-secondary)',
              padding: '4px 10px',
              fontSize: '0.6875rem',
              fontWeight: 700,
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
            className="project-tab-btn"
          >
            View Logs
          </button>
        </nav>

        <header className="bourntec-hero" style={{ padding: '24px 16px 12px' }}>
          <div className="bourntec-hero-badge" style={{ padding: '2px 8px', fontSize: '0.625rem', marginBottom: '8px' }}>
            <Cpu size={10} />
            <span>DSuite Compilation Engine Live</span>
          </div>
          <h1 className="bourntec-hero-title" style={{ fontSize: '1.5rem', marginBottom: '8px', lineHeight: 1.2 }}>
            Software, Engineered by <span style={{ color: 'var(--primary-light)', display: 'inline' }}>Autonomous Intelligence.</span>
          </h1>
          <p className="bourntec-hero-desc" style={{ fontSize: '0.75rem', marginBottom: '12px', lineHeight: 1.4 }}>
            Explore the production codebase and live endpoints compiled automatically from your business specifications.
          </p>
          <div className="bourntec-hero-ctas" style={{ gap: '8px', marginBottom: '4px' }}>
            <a href="#showcase" className="btn btn-primary" style={{ fontSize: '0.6875rem', padding: '6px 14px', borderRadius: '8px' }}>
              Explore Sandbox
            </a>
            <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="btn btn-secondary" style={{ fontSize: '0.6875rem', padding: '6px 14px', borderRadius: '8px' }}>
              View Repo
            </a>
          </div>
        </header>

        <section id="showcase" className="bourntec-showcase-section" style={{ padding: '16px 16px 24px' }}>
          <div className="section-header" style={{ marginBottom: '12px' }}>
            <h2 style={{ fontSize: '1.125rem', fontWeight: 800, textAlign: 'center' }}>Live Sandbox</h2>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', textAlign: 'center', margin: 0 }}>
              Interact with the active modules generated by DSuite.
            </p>
          </div>

          <div className="bourntec-showcase-panel">
            <div className="bourntec-showcase-header" style={{ padding: '8px 12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span className="status-dot" style={{ width: '6px', height: '6px' }}></span>
                <span style={{ fontSize: '0.6875rem', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  bourntec-sandbox-v1 // active_session
                </span>
              </div>
              <span className="badge badge-success" style={{ fontSize: '0.5rem', padding: '1px 4px' }}>
                Online
              </span>
            </div>

            <div className="bourntec-showcase-body" style={{ minHeight: 'auto', maxHeight: 'none', height: 'auto' }}>
              <div className="bourntec-showcase-tasks" style={{ padding: '12px', overflowY: 'visible' }}>
                {SHOWCASE_TASKS.map((task, idx) => (
                  <div 
                    key={task.id}
                    className={`bourntec-showcase-task-card ${showcaseTaskIndex === idx ? 'active' : ''}`}
                    onClick={() => setShowcaseTaskIndex(idx)}
                    style={{ padding: '8px 10px', borderRadius: '8px' }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2px' }}>
                      <span style={{ fontWeight: 700, fontSize: '0.6875rem', color: showcaseTaskIndex === idx ? 'var(--primary-light)' : 'var(--text-secondary)' }}>
                        {task.title}
                      </span>
                      <span className="badge badge-primary" style={{ fontSize: '0.5rem', padding: '0px 3px', textTransform: 'none' }}>
                        {task.badge}
                      </span>
                    </div>
                    <p style={{ fontSize: '0.625rem', color: 'var(--text-tertiary)', margin: 0, lineHeight: 1.3 }}>
                      {task.desc}
                    </p>
                  </div>
                ))}
              </div>

              <div className="bourntec-showcase-details" style={{ padding: '12px', overflowY: 'visible' }}>
                <div style={{ fontSize: '0.625rem', color: 'var(--text-tertiary)', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '4px', display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span>Compiled: <strong style={{ color: 'var(--primary-light)', fontFamily: 'var(--font-mono)' }}>{SHOWCASE_TASKS[showcaseTaskIndex].file}</strong></span>
                  <span style={{ color: 'var(--success)' }}>Syntax OK</span>
                </div>

                <pre style={{ margin: '0 0 6px', padding: '6px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '6px', fontFamily: 'var(--font-mono)', fontSize: '0.625rem', lineHeight: 1.4, color: '#e2e8f0', overflow: 'auto', maxHeight: '120px', textAlign: 'left' }}>
                  <code>{CODE_FILES[SHOWCASE_TASKS[showcaseTaskIndex].file]}</code>
                </pre>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                  <pre style={{ margin: 0, padding: '6px 8px', background: '#000', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '6px', fontFamily: 'var(--font-mono)', fontSize: '0.5625rem', lineHeight: 1.3, color: 'var(--success)', overflowX: 'auto', textAlign: 'left', maxHeight: '80px' }}>
                    {SHOWCASE_TASKS[showcaseTaskIndex].log}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="features" className="bourntec-features-section" style={{ padding: '12px 16px 24px' }}>
          <h3 className="bourntec-features-title" style={{ fontSize: '1.25rem', marginBottom: '16px' }}>Platform Features</h3>
          <div className="bourntec-features-grid" style={{ gap: '12px' }}>
            <div className="bourntec-feature-card" style={{ padding: '14px', borderRadius: '12px' }}>
              <div className="bourntec-feature-icon" style={{ width: '32px', height: '32px' }}>
                <CheckCircle2 size={14} />
              </div>
              <h4 style={{ fontSize: '0.8125rem', fontWeight: 700, margin: 0 }}>Self-Healing Builds</h4>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.4 }}>
                AI agents automatically refactor build errors to achieve 100% compilation safety.
              </p>
            </div>

            <div className="bourntec-feature-card" style={{ padding: '14px', borderRadius: '12px' }}>
              <div className="bourntec-feature-icon" style={{ width: '32px', height: '32px' }}>
                <Layers size={14} />
              </div>
              <h4 style={{ fontSize: '0.8125rem', fontWeight: 700, margin: 0 }}>Schema Inference</h4>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.4 }}>
                Database keys, indices, and tables are compiled directly from requirement documents.
              </p>
            </div>

            <div className="bourntec-feature-card" style={{ padding: '14px', borderRadius: '12px' }}>
              <div className="bourntec-feature-icon" style={{ width: '32px', height: '32px' }}>
                <Terminal size={14} />
              </div>
              <h4 style={{ fontSize: '0.8125rem', fontWeight: 700, margin: 0 }}>Zero-Trust Security</h4>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.4 }}>
                Sandbox code compiled within isolated virtual node clusters audits dependencies on merge.
              </p>
            </div>
          </div>
        </section>

        <section id="telemetry" className="bourntec-metrics-section" style={{ padding: '0 16px 24px' }}>
          <div className="bourntec-metrics-grid" style={{ gap: '10px' }}>
            <div className="bourntec-metric-card" style={{ padding: '10px', borderRadius: '10px' }}>
              <div className="bourntec-metric-value" style={{ fontSize: '1.5rem' }}>15.2h</div>
              <div className="bourntec-metric-label" style={{ fontSize: '0.625rem' }}>Swarm active time</div>
            </div>

            <div className="bourntec-metric-card" style={{ padding: '10px', borderRadius: '10px' }}>
              <div className="bourntec-metric-value" style={{ fontSize: '1.5rem' }}>100%</div>
              <div className="bourntec-metric-label" style={{ fontSize: '0.625rem' }}>Compile success</div>
            </div>

            <div className="bourntec-metric-card" style={{ padding: '10px', borderRadius: '10px' }}>
              <div className="bourntec-metric-value" style={{ fontSize: '1.5rem' }}>3</div>
              <div className="bourntec-metric-label" style={{ fontSize: '0.625rem' }}>AI agents swarm</div>
            </div>

            <div className="bourntec-metric-card" style={{ padding: '10px', borderRadius: '10px' }}>
              <div className="bourntec-metric-value" style={{ fontSize: '1.5rem' }}>4.8s</div>
              <div className="bourntec-metric-label" style={{ fontSize: '0.625rem' }}>Build latency</div>
            </div>
          </div>
        </section>

        <footer className="bourntec-footer" style={{ padding: '16px', fontSize: '0.6875rem' }}>
          © 2026 Bourntec Solutions. Delivered via DSuite compilation.
        </footer>
      </div>
    );
  };

  const renderStepContent = (step) => {
    switch (step) {
      case 0: return renderIngest();
      case 1: return renderBlueprint();
      case 2: return renderTasks();
      case 3: return renderExecution();
      case 4: {
        if (isAppLaunched) {
          return renderBourntecLanding();
        }
        return renderDeployment();
      }
      default: return null;
    }
  };
  return (
    <section id="tour" className="section" style={{ borderBottom: '1px solid var(--border)', background: 'rgba(6, 6, 9, 0.2)' }}>
      <div className="container">
        <div className="section-header">
          <div className="section-badge">How It Works</div>
          <h2 className="section-title">
            The Agentic Compilation Tour
          </h2>
          <p className="section-description">
            Explore the exact steps DSuite takes to convert your document into a deployed Express and database sandbox.
          </p>
        </div>

        {/* Video Tour Grid */}
        <div className="tour-grid">
          
          {/* Step Sidebar */}
          <div className="tour-sidebar">
            {TOUR_STEPS.map((step) => {
              const StepIcon = step.icon;
              const isActive = activeStep === step.id;
              return (
                <button
                  key={step.id}
                  onClick={() => handleStepSelect(step.id)}
                  className={`tour-step-btn ${isActive ? 'active' : ''}`}
                >
                  <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'flex-start' }}>
                    <div className={`tour-step-icon-wrapper ${isActive ? 'active' : ''}`}>
                      <StepIcon size={16} />
                    </div>
                    <div style={{ textAlign: 'left' }}>
                      <div className="tour-step-title">{step.title}</div>
                      <div className="tour-step-subtitle">{step.subtitle}</div>
                      {isActive && (
                        <p className="tour-step-desc-active reveal-on-scroll reveal-visible">
                          {step.description}
                        </p>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
            
            {/* Play Pause Controls */}
            <div className="autoplay-control-bar" style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '12px', 
              marginTop: 'var(--space-4)', 
              padding: '8px 16px',
              background: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid rgba(255, 255, 255, 0.05)',
              borderRadius: '12px',
              backdropFilter: 'blur(4px)'
            }}>
              <button 
                onClick={() => setIsPlaying(!isPlaying)}
                className={`btn ${isPlaying ? 'btn-autoplay-active' : 'btn-secondary'}`} 
                style={{ 
                  borderRadius: '50%', 
                  width: '32px', 
                  height: '32px', 
                  padding: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: isPlaying ? 'rgba(139, 92, 246, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                  border: isPlaying ? '1px solid rgba(139, 92, 246, 0.4)' : '1px solid rgba(255, 255, 255, 0.1)',
                  color: isPlaying ? '#a78bfa' : '#94a3b8',
                  boxShadow: isPlaying ? '0 0 10px rgba(139, 92, 246, 0.2)' : 'none'
                }}
              >
                {isPlaying ? <Pause size={14} /> : <Play size={14} />}
              </button>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span className="status-dot" style={{ 
                  width: '6px', 
                  height: '6px', 
                  background: isPlaying ? '#10b981' : '#f59e0b',
                  animation: isPlaying ? 'pulse-dot 2s ease-in-out infinite' : 'none'
                }}></span>
                <span style={{ fontSize: '0.75rem', color: isPlaying ? 'var(--text-secondary)' : 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                  {isPlaying ? 'Auto-play Mode Active' : 'Simulation Paused'}
                </span>
              </div>
            </div>
          </div>

          <div className="tour-viewport-container">
            <div className="tour-viewport">
              <div className="viewport-header">
                <div className="viewport-dots">
                  <span className="dot red"></span>
                  <span className="dot yellow"></span>
                  <span className="dot green"></span>
                </div>
                <div className="viewport-address">
                {activeStep === 4 && isAppLaunched 
                  ? 'bourntec.sandbox.local/home' 
                  : `dsuite.internal/compiler-node-${activeStep + 1}`}
              </div>
            </div>
            <div className="viewport-body" style={{ overflowY: activeStep === 4 && isAppLaunched ? 'hidden' : 'auto' }}>
              {renderStepContent(activeStep)}
            </div>
          </div>
        </div>

      </div>
    </div>
  </section>
  );
}
