import React, { useEffect, useRef, useState } from 'react';
import { Zap, ArrowRight, Play, Sparkles, Code, Rocket, Shield, Globe, Cpu, MessageSquare, Layout, Palette, ShoppingBag, Megaphone, Briefcase } from 'lucide-react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import bourntecLogo from '../../assets/bourntec_logo.png';

gsap.registerPlugin(ScrollTrigger);

const LandingPage = ({ onGetStarted, onSignIn }) => {
  const pageRef = useRef(null);
  const navRef = useRef(null);
  const [navScrolled, setNavScrolled] = useState(false);

  useEffect(() => {
    const ctx = gsap.context(() => {
      // ── Hero Animations (timeline for sequential reveal) ──
      const heroTl = gsap.timeline({ defaults: { ease: 'power3.out' } });

      heroTl
        .to('.hero-badge', { opacity: 1, y: 0, duration: 0.6, delay: 0.3 })
        .to('.hero-title', { opacity: 1, y: 0, duration: 0.7 }, '-=0.3')
        .to('.hero-subtitle', { opacity: 1, y: 0, duration: 0.6 }, '-=0.4')
        .to('.hero-cta', { opacity: 1, y: 0, duration: 0.6 }, '-=0.3')
        .to('.hero-stats', { opacity: 1, y: 0, duration: 0.7 }, '-=0.3');

      // Set initial states for hero elements
      gsap.set(['.hero-badge', '.hero-title', '.hero-subtitle', '.hero-cta', '.hero-stats'], {
        y: 30,
      });

      // ── Floating orbs ──
      gsap.to('.hero-orb-1', {
        x: 40,
        y: -30,
        duration: 8,
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut',
      });
      gsap.to('.hero-orb-2', {
        x: -35,
        y: 25,
        duration: 10,
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut',
      });
      gsap.to('.hero-orb-3', {
        x: 30,
        y: -20,
        duration: 7,
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut',
      });

      // ── Showcase reveal ──
      ScrollTrigger.create({
        trigger: '.showcase-wrapper',
        start: 'top 85%',
        onEnter: () => {
          gsap.to('.showcase-wrapper', {
            opacity: 1,
            y: 0,
            duration: 1,
            ease: 'power3.out',
          });
        },
        once: true,
      });
      gsap.set('.showcase-wrapper', { y: 60 });

      // ── Feature cards staggered reveal ──
      ScrollTrigger.batch('.feature-card', {
        start: 'top 85%',
        onEnter: (batch) => {
          gsap.to(batch, {
            opacity: 1,
            y: 0,
            duration: 0.6,
            stagger: 0.1,
            ease: 'power3.out',
          });
        },
        once: true,
      });

      // ── How It Works steps ──
      ScrollTrigger.batch('.how-step', {
        start: 'top 85%',
        onEnter: (batch) => {
          gsap.to(batch, {
            opacity: 1,
            y: 0,
            duration: 0.7,
            stagger: 0.15,
            ease: 'power3.out',
          });
        },
        once: true,
      });

      // ── Use Case cards ──
      ScrollTrigger.batch('.use-case-card', {
        start: 'top 85%',
        onEnter: (batch) => {
          gsap.to(batch, {
            opacity: 1,
            y: 0,
            duration: 0.6,
            stagger: 0.1,
            ease: 'power3.out',
          });
        },
        once: true,
      });

      // ── CTA section ──
      ScrollTrigger.create({
        trigger: '.cta-container',
        start: 'top 85%',
        onEnter: () => {
          gsap.to('.cta-container', {
            opacity: 1,
            y: 0,
            duration: 0.8,
            ease: 'power3.out',
          });
        },
        once: true,
      });
      gsap.set('.cta-container', { y: 40 });

    }, pageRef);

    // ── Nav scroll handling ──
    const handleScroll = () => {
      setNavScrolled(window.scrollY > 50);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      ctx.revert();
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  const features = [
    {
      icon: <MessageSquare size={24} />,
      iconClass: 'feature-icon-purple',
      title: 'Natural Language to Code',
      desc: 'Describe what you want in plain English. Our AI understands context and generates production-ready code instantly.',
    },
    {
      icon: <Code size={24} />,
      iconClass: 'feature-icon-pink',
      title: 'Live Preview & Editing',
      desc: 'See your changes in real-time with our built-in preview. Click any element to edit it visually or through prompts.',
    },
    {
      icon: <Rocket size={24} />,
      iconClass: 'feature-icon-blue',
      title: 'One-Click Deploy',
      desc: 'Deploy your project to production with a single click. No configuration needed — we handle the infrastructure.',
    },
    {
      icon: <Shield size={24} />,
      iconClass: 'feature-icon-emerald',
      title: 'Version Control Built-in',
      desc: 'Full Git integration with branch management, commit history, and collaboration tools out of the box.',
    },
    {
      icon: <Globe size={24} />,
      iconClass: 'feature-icon-orange',
      title: 'Multi-File Projects',
      desc: 'Generate complete multi-file applications with proper folder structures, not just single-page snippets.',
    },
    {
      icon: <Cpu size={24} />,
      iconClass: 'feature-icon-cyan',
      title: 'Smart Iterations',
      desc: 'Refine and iterate on existing code through conversation. The AI remembers context and builds on previous work.',
    },
  ];

  const useCases = [
    {
      icon: <Globe size={24} />,
      title: 'SaaS Platforms',
      desc: 'High-conversion landing pages and multi-page marketing sites with complex forms.',
      color: 'linear-gradient(135deg, #8B5CF6, #7C3AED)',
    },
    {
      icon: <Layout size={24} />,
      title: 'Admin Dashboards',
      desc: 'Powerful data management systems with interactive charts and responsive tables.',
      color: 'linear-gradient(135deg, #EC4899, #DB2777)',
    },
    {
      icon: <Palette size={24} />,
      title: 'Creative Portfolios',
      desc: 'Showcase your work with stunning, animated portfolios that capture attention.',
      color: 'linear-gradient(135deg, #3B82F6, #2563EB)',
    },
    {
      icon: <ShoppingBag size={24} />,
      title: 'E-commerce',
      desc: 'Engaging shopping experiences with product grids, filters, and seamless flows.',
      color: 'linear-gradient(135deg, #10B981, #059669)',
    },
    {
      icon: <Megaphone size={24} />,
      title: 'Marketing Sites',
      desc: 'Fast, SEO-optimized campaign sites built for performance and core web vitals.',
      color: 'linear-gradient(135deg, #F59E0B, #D97706)',
    },
    {
      icon: <Briefcase size={24} />,
      title: 'Internal Tools',
      desc: 'Custom workflows and automated systems tailored for your business needs.',
      color: 'linear-gradient(135deg, #6366F1, #4F46E5)',
    },
  ];

  return (
    <div className="landing-page" ref={pageRef}>
      {/* ── Navigation ── */}
      <nav className={`landing-nav ${navScrolled ? 'scrolled' : ''}`} ref={navRef}>
        <div className="nav-logo">
          <img src={bourntecLogo} alt="Bourntec" />
          <div className="nav-logo-divider" />
          <div className="nav-logo-text">
            <div className="nav-logo-icon">
              <Zap />
            </div>
            <span className="nav-logo-name">VibeCoding</span>
          </div>
        </div>
        <div className="nav-links">
          <a href="#features">Features</a>
          <a href="#how-it-works">How It Works</a>
          <a href="#capabilities">Capabilities</a>
        </div>
        <div className="nav-actions">
          <button className="nav-btn-signin" onClick={onSignIn}>Sign In</button>
          <button className="nav-btn-start" onClick={onGetStarted}>
            Get Started <ArrowRight size={14} />
          </button>
        </div>
      </nav>

      {/* ── Hero Section ── */}
      <section className="hero-section">
        <div className="hero-bg">
          <div className="hero-orb hero-orb-1" />
          <div className="hero-orb hero-orb-2" />
          <div className="hero-orb hero-orb-3" />
          <div className="hero-grid" />
        </div>
        <div className="hero-content">
          <div className="hero-badge">
            <span className="hero-badge-dot" />
            Now powered by advanced AI models
          </div>
          <h1 className="hero-title">
            <span className="hero-title-gradient">
              Build Anything<br />With Just Words
            </span>
          </h1>
          <p className="hero-subtitle">
            Transform your ideas into production-ready web applications using natural language.
            No boilerplate. No configuration. Just describe and deploy.
          </p>
          <div className="hero-cta">
            <button className="hero-btn-primary" onClick={onGetStarted}>
              <Sparkles size={18} />
              Start Building Free
            </button>
            <button className="hero-btn-secondary" onClick={() => {
              document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' });
            }}>
              <Play size={18} />
              See How It Works
            </button>
          </div>
          <div className="hero-stats">
            <div className="hero-stat">
              <div className="hero-stat-value">10x</div>
              <div className="hero-stat-label">Faster Development</div>
            </div>
            <div className="hero-stat-divider" />
            <div className="hero-stat">
              <div className="hero-stat-value">500+</div>
              <div className="hero-stat-label">Projects Deployed</div>
            </div>
            <div className="hero-stat-divider" />
            <div className="hero-stat">
              <div className="hero-stat-value">99%</div>
              <div className="hero-stat-label">Uptime</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── App Showcase ── */}
      <section className="showcase-section">
        <div className="showcase-wrapper">
          <div className="showcase-frame">
            <div className="showcase-topbar">
              <div className="showcase-dots">
                <span /><span /><span />
              </div>
              <div className="showcase-url">vibecoding.bourntec.com</div>
            </div>
            <div className="showcase-body">
              <div className="mock-app">
                <div className="mock-preview">
                  <div className="mock-preview-content">
                    <div className="mock-preview-title">Your App, Live</div>
                    <div className="mock-preview-text">Real-time preview updates as you chat with the AI</div>
                    <div className="mock-preview-btn">Get Started →</div>
                  </div>
                </div>
                <div className="mock-sidebar">
                  <div className="mock-chat-bubble mock-chat-user">
                    Create a stunning landing page with a hero section, animated gradient background, and a pricing table
                  </div>
                  <div className="mock-chat-bubble mock-chat-ai">
                    I'll build that for you! Creating a modern landing page with:<br /><br />
                    ✦ Animated gradient hero<br />
                    ✦ Feature highlights<br />
                    ✦ Pricing table with 3 tiers<br />
                    ✦ Responsive design
                  </div>
                  <div className="mock-chat-bubble mock-chat-user">
                    Make the pricing cards glassmorphic
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="showcase-glow" />
        </div>
      </section>

      {/* ── Features Section ── */}
      <section className="features-section" id="features">
        <div className="section-header">
          <div className="section-tag">
            <Sparkles size={14} />
            Features
          </div>
          <h2 className="section-title">Everything You Need to Ship Fast</h2>
          <p className="section-desc">
            From idea to deployment in minutes. VibeCoding gives you the complete toolkit to build, preview, and launch web applications.
          </p>
        </div>
        <div className="features-grid">
          {features.map((feature, i) => (
            <div className="feature-card" key={i}>
              <div className={`feature-icon ${feature.iconClass}`}>
                {feature.icon}
              </div>
              <h3>{feature.title}</h3>
              <p>{feature.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── How It Works ── */}
      <section className="how-section" id="how-it-works">
        <div className="section-header">
          <div className="section-tag">
            <Rocket size={14} />
            How It Works
          </div>
          <h2 className="section-title">Three Steps to Launch</h2>
          <p className="section-desc">
            No complex setup. No steep learning curve. Just describe, preview, and deploy.
          </p>
        </div>
        <div className="how-steps">
          <div className="how-step">
            <div className="how-step-number step-1">1</div>
            <h3>Describe Your Vision</h3>
            <p>Tell the AI what you want to build using natural language. Be as specific or as general as you like.</p>
          </div>
          <div className="how-step">
            <div className="how-step-number step-2">2</div>
            <h3>Preview & Refine</h3>
            <p>Watch your application come to life in real-time. Click to edit elements or chat to make iterative changes.</p>
          </div>
          <div className="how-step">
            <div className="how-step-number step-3">3</div>
            <h3>Deploy Instantly</h3>
            <p>One click to push your project live. We handle hosting, SSL, and infrastructure — you focus on building.</p>
          </div>
        </div>
      </section>

      {/* ── Use Cases Section ── */}
      <section className="proof-section" id="capabilities">
        <div className="section-header">
          <div className="section-tag">
            <Sparkles size={14} />
            Capabilities
          </div>
          <h2 className="section-title">Built for Every Use Case</h2>
          <p className="section-desc">
            VibeCoding is versatile enough to handle everything from simple marketing sites to complex web applications.
          </p>
        </div>
        <div className="proof-grid">
          {useCases.map((useCase, i) => (
            <div className="proof-card use-case-card" key={i}>
              <div className="feature-icon" style={{ background: useCase.color, color: 'white', marginBottom: '20px' }}>
                {useCase.icon}
              </div>
              <h3 style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '20px', fontWeight: '700', marginBottom: '10px' }}>
                {useCase.title}
              </h3>
              <p style={{ fontSize: '14px', color: 'rgba(255, 255, 255, 0.4)', lineHeight: '1.6' }}>
                {useCase.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Final CTA ── */}
      <section className="cta-section">
        <div className="cta-container">
          <h2 className="cta-title">Ready to Build Something Amazing?</h2>
          <p className="cta-desc">
            Start turning your ideas into real, deployed applications today. No credit card required.
          </p>
          <button className="cta-btn" onClick={onGetStarted}>
            Get Started Free <ArrowRight size={18} />
          </button>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="landing-footer">
        <div className="footer-content">
          <div className="footer-brand">
            <img src={bourntecLogo} alt="Bourntec" />
            <span>VibeCoding by Bourntec Solutions</span>
          </div>
          <div className="footer-links">
            <a href="#features">Features</a>
            <a href="#how-it-works">How It Works</a>
            <a href="#capabilities">Capabilities</a>
          </div>
          <div className="footer-copy">
            © {new Date().getFullYear()} Bourntec Solutions. All rights reserved.
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
