import React, { useState } from 'react';
import Navbar from './components/Navbar';
import Hero from './components/Hero';
import TourPlayer from './components/TourPlayer';
import Features from './components/Features';
import Orchestrator from './components/Orchestrator';
import Footer from './components/Footer';
import './App.css';

export default function App() {
  const [selectedMode, setSelectedMode] = useState('vibe_coding');

  return (
    <>
      {/* Animated Background */}
      <div className="animated-bg"></div>
      <div className="grid-pattern"></div>
      
      {/* Navigation */}
      <Navbar />

      {/* Hero Section - shows simulation based on selected mode */}
      <Hero selectedMode={selectedMode} />

      {/* Tour Player Section */}
      <TourPlayer />

      {/* Features Section */}
      <Features />

      {/* Orchestrator Section - user selects execution mode here */}
      <Orchestrator onModeChange={setSelectedMode} />

      {/* CTA Section */}
      <section className="section" style={{
        background: 'linear-gradient(180deg, transparent 0%, rgba(139, 92, 246, 0.05) 100%)'
      }}>
        <div className="container" style={{ textAlign: 'center' }}>
          <h2 className="section-title" style={{ marginBottom: 'var(--space-6)' }}>
            Ready to Transform Your<br />Development Workflow?
          </h2>
          <p style={{
            fontSize: '1.125rem',
            color: 'var(--text-secondary)',
            maxWidth: '600px',
            margin: '0 auto var(--space-8)',
            lineHeight: 1.7
          }}>
            Join teams using DSuite to accelerate development with AI agents while maintaining quality and control.
          </p>
          <div style={{ display: 'flex', gap: 'var(--space-4)', justifyContent: 'center', flexWrap: 'wrap' }}>
            <button className="btn btn-primary" style={{ fontSize: '1.125rem', padding: '1rem 2.5rem' }}>
              Get Started Free
            </button>
            <button className="btn btn-secondary" style={{ fontSize: '1.125rem', padding: '1rem 2.5rem' }}>
              Schedule Demo
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <Footer />
    </>
  );
}
