import React, { useState, useEffect, useRef } from 'react';
import { Brain, Shield, Zap, GitBranch, Database, Code2 } from 'lucide-react';

const FEATURES = [
  {
    icon: Brain,
    title: 'AI Architecture Generation',
    description: 'Automatically generates technical specifications, database schemas, and API designs from business requirements.'
  },
  {
    icon: Shield,
    title: 'Governance & Compliance',
    description: 'Built-in screening for security, namespace assignment, and dependency audits with configurable gates.'
  },
  {
    icon: Zap,
    title: 'Multi-Agent Orchestration',
    description: 'Coordinate pools of 20-100+ specialized agents with intelligent load balancing and file locking.'
  },
  {
    icon: GitBranch,
    title: 'Smart Task Breakdown',
    description: 'Decomposes complex projects into sequenced, dependency-aware backlog items with effort estimation.'
  },
  {
    icon: Database,
    title: 'Context Lake Integration',
    description: 'Centralized knowledge graph of your codebase, documentation, and architectural decisions.'
  },
  {
    icon: Code2,
    title: '5 Execution Modes',
    description: 'From fully manual to AI-first autonomous—choose the automation level that fits your workflow.'
  }
];

export default function Features() {
  const [isVisible, setIsVisible] = useState(false);
  const sectionRef = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setIsVisible(true);
        observer.unobserve(entry.target);
      }
    }, { threshold: 0.1 });

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => {
      if (sectionRef.current) {
        observer.unobserve(sectionRef.current);
      }
    };
  }, []);

  return (
    <section id="features" className="section" ref={sectionRef}>
      <div className="container">
        <div className={`section-header reveal-on-scroll ${isVisible ? 'reveal-visible' : ''}`}>
          <div className="section-badge">Platform Capabilities</div>
          <h2 className="section-title">
            Everything You Need for<br />Agentic Development
          </h2>
          <p className="section-description">
            From requirements analysis to production deployment, DSuite handles the entire SDLC with AI agents while keeping humans in control.
          </p>
        </div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: 'var(--space-6)'
        }}>
          {FEATURES.map((feature, idx) => {
            const Icon = feature.icon;
            return (
              <div 
                key={idx} 
                className={`glass-card reveal-on-scroll delay-${idx + 1} ${isVisible ? 'reveal-visible' : ''}`}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 'var(--space-4)'
                }}
              >
                <div style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '12px',
                  background: 'var(--gradient-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}>
                  <Icon size={24} color="white" />
                </div>
                <div>
                  <h3 style={{
                    fontSize: '1.25rem',
                    fontWeight: 700,
                    marginBottom: 'var(--space-2)'
                  }}>
                    {feature.title}
                  </h3>
                  <p style={{
                    color: 'var(--text-secondary)',
                    lineHeight: 1.6
                  }}>
                    {feature.description}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
