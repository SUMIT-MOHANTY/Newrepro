import React, { useState, useEffect, useRef } from 'react';
import { Lock, Users, Activity, Play, Pause, Code, Sparkles, Users2, Zap, RefreshCw, ArrowRight, CheckCircle2, FileCode, Terminal, Workflow } from 'lucide-react';

const EXECUTION_MODES = [
  {
    id: 'developer_only',
    name: 'Developer Only',
    automation: 'None',
    speed: 'Standard human calendar (months)',
    aiRole: 'Reference tool only - no code generation',
    humanRole: 'Full manual coding, manual reviews, standard timelines',
    color: '#71717a',
    timeline: '3-6 months for typical project',
    workflow: 'Opens Status Dashboard without AI agents. Traditional development workflow.',
    icon: Code
  },
  {
    id: 'ai_assist',
    name: 'AI Assist',
    automation: 'Low',
    speed: 'Standard human calendar',
    aiRole: 'Generates inline suggestions and autocompletions',
    humanRole: 'Developer triggers tab completion, validates all code',
    color: '#06b6d4',
    timeline: '2-4 months (human pace with AI quality boost)',
    workflow: 'Redirects to VS Code with N-Mod Extension. AI assists but doesn\'t write full files.',
    icon: Sparkles
  },
  {
    id: 'vibe_coding',
    name: 'Vibe Coding',
    automation: 'Medium',
    speed: '2-3x human speed',
    aiRole: 'Generates complete files and drafts from prompts',
    humanRole: 'Developer writes prompts, validates output, refines edge cases',
    color: '#8b5cf6',
    timeline: '4-6 weeks (prototyping speed)',
    workflow: 'Opens Bourntec Vibe Coding Platform. Developer describes intent in natural language, AI generates full implementations.',
    icon: Zap
  },
  {
    id: 'coexistence',
    name: 'Co-Existence',
    automation: 'High',
    speed: 'Hybrid: Faster than human, anchored to human calendar',
    aiRole: 'Auto-programs backend layers and specifications',
    humanRole: 'Manual approval gates for blueprints, monitors agents',
    color: '#f59e0b',
    timeline: '2-4 weeks (human-driven with AI acceleration)',
    workflow: 'Opens Status Dashboard with agents available for manual run. Human approves specs before execution.',
    icon: Users2
  },
  {
    id: 'ai_first',
    name: 'AI First (Sandbox)',
    automation: 'Full',
    speed: 'Machine-speed: 24/7 parallel execution',
    aiRole: 'Autonomous agents build, test, and patch',
    humanRole: 'Supervisor monitors dashboard logs only',
    color: '#22c55e',
    timeline: '3-5 DAYS for 100-task project',
    workflow: 'Opens Status Dashboard and auto-starts all agents. Massive parallelism with 20-100+ agents running simultaneously.',
    icon: RefreshCw
  }
];

const AGENT_SPECIALIZATION = [
  {
    pattern: 'Name-based',
    examples: ['agent_ui_05 → Frontend', 'agent_backend_03 → Backend', 'agent_devops_02 → DevOps'],
    description: 'Agents with keywords like frontend, ui, react, backend, api, devops are auto-classified'
  },
  {
    pattern: 'Numeric Range',
    examples: ['agent_01-10 → Full-Stack', 'agent_11-20 → Backend', 'agent_21-30 → Frontend'],
    description: 'Sequential numeric agents get specialized by number range'
  },
  {
    pattern: 'Manual Config',
    examples: ['API/Settings override', 'Custom role assignment'],
    description: 'Developers can manually assign agent specializations'
  },
  {
    pattern: 'AI Decision',
    examples: ['Master Agent analyzes task ratios', 'Dynamic redistribution'],
    description: 'AI evaluates workload and redistributes agent roles automatically'
  }
];

export default function Orchestrator({ onModeChange }) {
  const [selectedMode, setSelectedMode] = useState('vibe_coding');
  const [agentPool, setAgentPool] = useState(30);
  const [isRunning, setIsRunning] = useState(true);
  const [showSpecialization, setShowSpecialization] = useState(false);
  const [flowStep, setFlowStep] = useState(0);
  const [isVisible, setIsVisible] = useState(false);
  const sectionRef = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setIsVisible(true);
        observer.unobserve(entry.target);
      }
    }, { threshold: 0.05 });

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => {
      if (sectionRef.current) {
        observer.unobserve(sectionRef.current);
      }
    };
  }, []);

  const handleModeChange = (modeId) => {
    setSelectedMode(modeId);
    if (onModeChange) {
      onModeChange(modeId);
    }
    setFlowStep(0);
    setIsRunning(true);
  };

  const mode = EXECUTION_MODES.find(m => m.id === selectedMode);
  const ModeIcon = mode?.icon || Activity;

  // Animation for flow steps
  useEffect(() => {
    if (!isRunning) {
      setFlowStep(0);
      return;
    }

    const steps = mode.id === 'developer_only' ? 3 :
                  mode.id === 'ai_assist' ? 4 :
                  mode.id === 'vibe_coding' ? 6 :
                  mode.id === 'coexistence' ? 6 :
                  mode.id === 'ai_first' ? 5 : 3;

    if (flowStep < steps) {
      const timer = setTimeout(() => {
        setFlowStep(flowStep + 1);
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [isRunning, flowStep, mode.id]);


  // Flow steps for each mode
  const getFlowSteps = (modeId) => {
    switch(modeId) {
      case 'developer_only':
        return [
          { icon: Terminal, label: 'Open Status Dashboard', desc: 'AI agents disabled' },
          { icon: Code, label: 'Manual Development', desc: 'Human writes all code' },
          { icon: CheckCircle2, label: 'Standard Timeline', desc: '3-6 months completion' }
        ];
      case 'ai_assist':
        return [
          { icon: Terminal, label: 'Redirect to VS Code', desc: 'Opening IDE' },
          { icon: Sparkles, label: 'N-Mod Extension Active', desc: 'AI assist mode on' },
          { icon: Code, label: 'Developer Codes', desc: 'AI suggests on Tab' },
          { icon: CheckCircle2, label: 'Human-Paced Dev', desc: 'With AI quality boost' }
        ];
      case 'vibe_coding':
        return [
          { icon: Terminal, label: 'Open Vibe Platform', desc: 'Bourntec platform loading' },
          { icon: Workflow, label: 'Platform Ready', desc: 'Vibe coding initialized' },
          { icon: FileCode, label: 'Developer Prompts', desc: 'Natural language input' },
          { icon: Sparkles, label: 'AI Generates Files', desc: 'Complete implementations' },
          { icon: Code, label: 'Files Created', desc: 'webhook.js, tests generated' },
          { icon: CheckCircle2, label: '2-3x Speed', desc: 'Prototyping velocity' }
        ];
      case 'coexistence':
        return [
          { icon: Terminal, label: 'Open Dashboard', desc: 'Agents available' },
          { icon: Sparkles, label: 'AI Generates Spec', desc: 'Database schema drafted' },
          { icon: Users2, label: 'Awaiting Approval', desc: 'Human reviews blueprint' },
          { icon: CheckCircle2, label: 'Human Approves', desc: 'Schema validated ✓' },
          { icon: Zap, label: 'Agents Execute', desc: 'Parallel task execution' },
          { icon: CheckCircle2, label: 'Hybrid Speed', desc: '2-4 weeks completion' }
        ];
      case 'ai_first':
        return [
          { icon: Terminal, label: 'Initialize Pool', desc: `${agentPool} agents starting` },
          { icon: Zap, label: 'Auto-Start Agents', desc: '24/7 execution begins' },
          { icon: Lock, label: 'File Locks Active', desc: 'Conflict prevention on' },
          { icon: Workflow, label: 'Massive Parallelism', desc: '8 tasks running now' },
          { icon: CheckCircle2, label: 'Machine Speed', desc: '3-5 days completion' }
        ];
      default:
        return [];
    }
  };

  const flowSteps = getFlowSteps(mode.id);

  return (
    <section id="workflow" className={`section reveal-on-scroll ${isVisible ? 'reveal-visible' : ''}`} ref={sectionRef}>
      <div className="container">
        <div className="section-header">
          <div className="section-badge">Workflow</div>
          <h2 className="section-title">
            The Complete Logic Flow
          </h2>
          <p className="section-description">
            Observe how DSuite triggers the workflow, how Nxdune distributes tasks to the specialized agents, and how progress metrics flow back constantly.
          </p>
        </div>

        {/* Execution Modes */}
        <div style={{ marginBottom: 'var(--space-8)' }}>
          <h3 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: 'var(--space-5)', textAlign: 'center' }}>
            5 Execution Modes
          </h3>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 'var(--space-3)',
            marginBottom: 'var(--space-6)'
          }}>
            {EXECUTION_MODES.map(m => {
              const Icon = m.icon;
              return (
                <div
                  key={m.id}
                  onClick={() => handleModeChange(m.id)}
                  className="card"
                  style={{
                    cursor: 'pointer',
                    borderColor: selectedMode === m.id ? m.color : 'var(--border)',
                    background: selectedMode === m.id ? `${m.color}15` : 'var(--surface)',
                    padding: 'var(--space-4)',
                    textAlign: 'center',
                    transition: 'all 0.3s ease'
                  }}
                >
                  <div style={{
                    width: '40px',
                    height: '40px',
                    borderRadius: '10px',
                    background: m.color,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    margin: '0 auto var(--space-3)'
                  }}>
                    <Icon size={20} color="white" />
                  </div>
                  <div style={{ fontSize: '0.9375rem', fontWeight: 700, marginBottom: 'var(--space-1)' }}>
                    {m.name}
                  </div>
                  <div className="badge badge-primary" style={{ fontSize: '0.625rem' }}>
                    {m.automation}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Selected Mode Details */}
        {mode && (
          <div className="glass-card" style={{ padding: 'var(--space-4)', marginBottom: 'var(--space-6)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 'var(--space-4)', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
                  <div style={{
                    width: '48px',
                    height: '48px',
                    borderRadius: '12px',
                    background: mode.color,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}>
                    <ModeIcon size={24} color="white" />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.5rem', fontWeight: 700 }}>
                      {mode.name}
                    </h3>
                    <p style={{ fontSize: '0.875rem', color: 'var(--text-tertiary)' }}>
                      Automation: {mode.automation}
                    </p>
                  </div>
                </div>
                <div style={{ 
                  padding: 'var(--space-3)', 
                  background: `${mode.color}15`, 
                  borderRadius: '8px',
                  border: `1px solid ${mode.color}40`,
                  marginTop: 'var(--space-3)'
                }}>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                    ⏱️ <strong>Timeline:</strong> {mode.timeline}
                  </div>
                </div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)', marginBottom: 'var(--space-5)' }}>
              <div>
                <div style={{ 
                  fontSize: '0.75rem', 
                  textTransform: 'uppercase', 
                  color: 'var(--text-tertiary)', 
                  marginBottom: 'var(--space-2)', 
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-2)'
                }}>
                  <Sparkles size={14} />
                  AI Role
                </div>
                <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '0.9375rem' }}>{mode.aiRole}</p>
              </div>
              <div>
                <div style={{ 
                  fontSize: '0.75rem', 
                  textTransform: 'uppercase', 
                  color: 'var(--text-tertiary)', 
                  marginBottom: 'var(--space-2)', 
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-2)'
                }}>
                  <Users size={14} />
                  Human Role
                </div>
                <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '0.9375rem' }}>{mode.humanRole}</p>
              </div>
            </div>

            <div style={{
              padding: 'var(--space-4)',
              background: 'var(--surface)',
              borderRadius: '10px',
              marginBottom: 'var(--space-4)'
            }}>
              <div style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: 'var(--space-2)' }}>
                🔄 Workflow
              </div>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '0.875rem' }}>
                {mode.workflow}
              </p>
            </div>

            <div style={{
              padding: 'var(--space-4)',
              background: 'var(--bg)',
              borderRadius: '10px',
              border: '1px solid var(--border)'
            }}>
              <div style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: 'var(--space-2)' }}>
                ⚡ Execution Speed
              </div>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '0.875rem' }}>
                {mode.speed}
              </p>
            </div>

            <div style={{
              marginTop: 'var(--space-5)',
              padding: 'var(--space-6)',
              background: 'var(--bg)',
              borderRadius: '12px',
              border: '1px solid var(--border)'
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 'var(--space-5)'
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-2)',
                  color: isRunning ? 'var(--success)' : 'var(--text-tertiary)'
                }}>
                  <div className={isRunning ? "status-dot" : ""} style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    background: isRunning ? 'var(--success)' : 'var(--text-tertiary)',
                    animation: isRunning ? 'pulse-dot 2s ease-in-out infinite' : 'none'
                  }}></div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem', fontWeight: 600 }}>
                    {isRunning ? `SIMULATING: ${mode.name.toUpperCase()}` : 'SIMULATION: IDLE'}
                  </span>
                </div>
                <span style={{ 
                  fontSize: '0.875rem', 
                  color: 'var(--text-tertiary)',
                  fontFamily: 'var(--font-mono)'
                }}>
                  Step {isRunning ? Math.min(flowStep, flowSteps.length) : 0} / {flowSteps.length}
                </span>
              </div>

              {/* Visual Flow Animation */}
              <div style={{
                overflowX: 'auto',
                width: '100%',
                marginBottom: 'var(--space-6)',
                padding: 'var(--space-2) 0'
              }}>
                <div style={{
                  position: 'relative',
                  minWidth: '540px',
                  width: '100%',
                  padding: 'var(--space-2) 0'
                }}>
                  {/* Connector line background */}
                  <div style={{
                    position: 'absolute',
                    top: '24px', // middle of 44px circle
                    left: '45px', // center of first step (90px width / 2)
                    right: '45px',
                    height: '2px',
                    background: 'var(--border)',
                    zIndex: 1
                  }} />
                  
                  {/* Active animated connector line */}
                  <div style={{
                    position: 'absolute',
                    top: '24px',
                    left: '45px',
                    right: '45px',
                    height: '2px',
                    zIndex: 2,
                    pointerEvents: 'none'
                  }}>
                    <div style={{
                      height: '100%',
                      background: `linear-gradient(90deg, ${mode.color} 0%, var(--success) 100%)`,
                      width: `${isRunning ? (Math.min(flowStep, flowSteps.length - 1) / (flowSteps.length - 1)) * 100 : 0}%`,
                      transition: 'width 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
                      boxShadow: isRunning ? `0 0 8px ${mode.color}` : 'none'
                    }} />
                  </div>

                  {/* Steps wrapper */}
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    position: 'relative',
                    zIndex: 3,
                    width: '100%'
                  }}>
                    {flowSteps.map((step, idx) => {
                      const StepIcon = step.icon;
                      const isActive = isRunning && idx === flowStep;
                      const isCompleted = isRunning && idx < flowStep;
                      const isUpcoming = !isRunning || idx > flowStep;
                      
                      return (
                        <div
                          key={idx}
                          style={{
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            width: '90px',
                            opacity: isUpcoming ? 0.35 : 1,
                            transform: isActive ? 'scale(1.05)' : 'scale(1)',
                            transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
                            animation: (isCompleted || isActive) ? 'slide-in 0.5s ease-out' : 'none',
                            position: 'relative'
                          }}
                        >
                          {/* Glow effect for active step */}
                          {isActive && (
                            <div style={{
                              position: 'absolute',
                              top: -5,
                              left: '50%',
                              transform: 'translateX(-50%)',
                              width: '60px',
                              height: '60px',
                              borderRadius: '50%',
                              background: `radial-gradient(circle, ${mode.color}40 0%, transparent 70%)`,
                              animation: 'pulse 2s ease-in-out infinite',
                              pointerEvents: 'none'
                            }} />
                          )}
                          
                          <div style={{
                            width: '44px',
                            height: '44px',
                            borderRadius: '50%',
                            background: isCompleted 
                              ? 'linear-gradient(135deg, var(--success) 0%, #059669 100%)' 
                              : isActive 
                                ? `linear-gradient(135deg, ${mode.color} 0%, ${mode.color}dd 100%)` 
                                : 'var(--surface)',
                            border: `2px solid ${isCompleted ? 'var(--success)' : isActive ? mode.color : 'var(--border)'}`,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            marginBottom: 'var(--space-2)',
                            transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
                            boxShadow: isActive 
                              ? `0 0 15px ${mode.color}60` 
                              : isCompleted 
                                ? '0 0 10px rgba(16, 185, 129, 0.4)' 
                                : 'none',
                            position: 'relative',
                            zIndex: 10
                          }}>
                            {isCompleted ? (
                              <CheckCircle2 
                                size={22} 
                                color="white" 
                              />
                            ) : (
                              <StepIcon 
                                size={22} 
                                color={isActive ? 'white' : 'var(--text-tertiary)'} 
                              />
                            )}
                            
                            {/* Step number badge */}
                            <div style={{
                              position: 'absolute',
                              top: '-4px',
                              right: '-4px',
                              width: '18px',
                              height: '18px',
                              borderRadius: '50%',
                              background: isCompleted ? 'var(--success)' : isActive ? mode.color : 'var(--border)',
                              border: '2px solid var(--bg)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '0.625rem',
                              fontWeight: 800,
                              color: 'white',
                              fontFamily: 'var(--font-mono)'
                            }}>
                              {idx + 1}
                            </div>
                          </div>
                          
                          <div style={{
                            fontSize: '0.6875rem',
                            fontWeight: 700,
                            textAlign: 'center',
                            marginBottom: '2px',
                            color: isCompleted || isActive ? 'var(--text)' : 'var(--text-tertiary)',
                            transition: 'color 0.3s ease',
                            lineHeight: 1.2
                          }}>
                            {step.label}
                          </div>
                          <div style={{
                            fontSize: '0.625rem',
                            textAlign: 'center',
                            color: isActive ? 'var(--text-secondary)' : 'var(--text-tertiary)',
                            lineHeight: 1.3,
                            maxWidth: '85px',
                            transition: 'color 0.3s ease'
                          }}>
                            {step.desc}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
              
              {/* Progress bar */}
              <div style={{
                width: '100%',
                height: '4px',
                background: 'var(--surface)',
                borderRadius: '2px',
                marginBottom: 'var(--space-4)',
                overflow: 'hidden',
                position: 'relative'
              }}>
                <div style={{
                  height: '100%',
                  background: `linear-gradient(90deg, ${mode.color} 0%, var(--success) 100%)`,
                  borderRadius: '2px',
                  width: `${isRunning ? (flowStep / flowSteps.length) * 100 : 0}%`,
                  transition: 'width 0.5s cubic-bezier(0.4, 0, 0.2, 1)',
                  boxShadow: `0 0 8px ${mode.color}40`,
                  position: 'relative',
                  overflow: 'hidden'
                }}>
                  {/* Shimmer effect */}
                  <div style={{
                    position: 'absolute',
                    top: 0,
                    left: '-100%',
                    width: '100%',
                    height: '100%',
                    background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent)',
                    animation: isRunning && flowStep > 0 && flowStep < flowSteps.length ? 'flow-line 1.5s ease-in-out infinite' : 'none'
                  }} />
                </div>
                <div style={{
                  position: 'absolute',
                  right: 'var(--space-2)',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  fontSize: '0.625rem',
                  fontWeight: 700,
                  color: 'var(--text-tertiary)',
                  fontFamily: 'var(--font-mono)'
                }}>
                  {isRunning ? Math.round((flowStep / flowSteps.length) * 100) : 0}%
                </div>
              </div>

              {/* Console Output */}
            </div>
          </div>
        )}

        {/* Agent Pool & File Lock Manager */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)', marginBottom: 'var(--space-8)' }}>
          {/* Agent Pool Control */}
          <div className="glass-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
              <div style={{
                width: '40px',
                height: '40px',
                borderRadius: '10px',
                background: 'var(--gradient-primary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <Users size={20} color="white" />
              </div>
              <div>
                <h3 style={{ fontSize: '1.125rem', fontWeight: 700 }}>Agent Pool</h3>
                <p style={{ fontSize: '0.875rem', color: 'var(--text-tertiary)' }}>Scale: {agentPool} agents</p>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-5)' }}>
              {[20, 30, 100].map(size => (
                <button
                  key={size}
                  onClick={() => setAgentPool(size)}
                  className={`btn ${agentPool === size ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ flex: 1, padding: 'var(--space-2) var(--space-3)', fontSize: '0.875rem' }}
                >
                  {size}
                </button>
              ))}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
              <div style={{ padding: 'var(--space-3)', background: 'var(--surface)', borderRadius: '10px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginBottom: 'var(--space-1)' }}>
                  Utilization Rate
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary-light)' }}>
                  {agentPool === 20 ? '65%' : agentPool === 30 ? '76%' : '88%'}
                </div>
              </div>
              <div style={{ padding: 'var(--space-3)', background: 'var(--surface)', borderRadius: '10px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginBottom: 'var(--space-1)' }}>
                  Load Balance Score
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--success)' }}>
                  {agentPool === 20 ? '82' : agentPool === 30 ? '88' : '94'}
                </div>
              </div>
            </div>
          </div>

          {/* File Lock Manager */}
          <div className="glass-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
              <div style={{
                width: '40px',
                height: '40px',
                borderRadius: '10px',
                background: 'var(--gradient-warm)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <Lock size={20} color="white" />
              </div>
              <div>
                <h3 style={{ fontSize: '1.125rem', fontWeight: 700 }}>File Lock Manager</h3>
                <p style={{ fontSize: '0.875rem', color: 'var(--text-tertiary)' }}>Prevents conflicts</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              {[
                { file: 'package.json', agent: 'agent_backend_12' },
                { file: 'auth.js', agent: 'agent_backend_15' },
                { file: 'schema.prisma', agent: 'agent_devops_02' }
              ].map((lock, idx) => (
                <div key={idx} style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: 'var(--space-2) var(--space-3)',
                  background: 'var(--surface)',
                  borderRadius: '8px',
                  fontSize: '0.8125rem'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                    <Lock size={14} color="#f59e0b" />
                    <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
                      {lock.file}
                    </code>
                  </div>
                  <span style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                    {lock.agent}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Agent Specialization */}
        <div className="glass-card" style={{ padding: 'var(--space-6)' }}>
          <div style={{ marginBottom: 'var(--space-5)', textAlign: 'center' }}>
            <h3 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: 'var(--space-2)' }}>
              Agent Specialization Assignment
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9375rem' }}>
              4-tier decision priority: Manual Config → AI Decision → Pattern Recognition → Default Fallback
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--space-4)' }}>
            {AGENT_SPECIALIZATION.map((spec, idx) => (
              <div key={idx} className="card" style={{ padding: 'var(--space-4)' }}>
                <div style={{ fontSize: '1rem', fontWeight: 700, marginBottom: 'var(--space-2)' }}>
                  {spec.pattern}
                </div>
                <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: 'var(--space-3)', lineHeight: 1.5 }}>
                  {spec.description}
                </div>
                <div style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-2)' }}>
                  {spec.examples.map((ex, i) => (
                    <div key={i} style={{ 
                      fontSize: '0.75rem', 
                      fontFamily: 'var(--font-mono)', 
                      color: 'var(--text-tertiary)',
                      marginBottom: 'var(--space-1)'
                    }}>
                      • {ex}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
