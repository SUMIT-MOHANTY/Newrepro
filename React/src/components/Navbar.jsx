import React, { useState, useEffect } from 'react';
import { Menu, X, Sparkles, Moon, Sun } from 'lucide-react';

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [theme, setTheme] = useState('dark');

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 50);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    // Check saved theme or system preference
    const savedTheme = localStorage.getItem('theme') || 'dark';
    setTheme(savedTheme);
    document.documentElement.setAttribute('data-theme', savedTheme);
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
  };

  return (
    <nav style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      zIndex: 100,
      padding: '1.25rem 0',
      background: scrolled ? (theme === 'dark' ? 'rgba(10, 10, 15, 0.85)' : 'rgba(255, 255, 255, 0.85)') : 'transparent',
      backdropFilter: scrolled ? 'blur(16px)' : 'none',
      borderBottom: scrolled ? '1px solid var(--border)' : 'none',
      transition: 'all 0.3s ease'
    }}>
      <div className="container" style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        {/* Logo */}
        <a href="#" style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.625rem',
          fontSize: '1.375rem',
          fontWeight: 800,
          fontFamily: 'var(--font-display)',
          color: 'var(--text)',
          textDecoration: 'none'
        }}>
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: '10px',
            background: 'var(--gradient-primary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Sparkles size={20} color="white" />
          </div>
          <span className="gradient-text">DSuite</span>
        </a>

        {/* Desktop Menu */}
        <div className="desktop-menu">
          <a href="#features" style={{
            color: 'var(--text-secondary)',
            fontWeight: 500,
            fontSize: '0.875rem',
            textDecoration: 'none',
            transition: 'color 0.2s'
          }} onMouseEnter={(e) => e.target.style.color = 'var(--text)'}
             onMouseLeave={(e) => e.target.style.color = 'var(--text-secondary)'}>
            Features
          </a>
          <a href="#workflow" style={{
            color: 'var(--text-secondary)',
            fontWeight: 500,
            fontSize: '0.875rem',
            textDecoration: 'none',
            transition: 'color 0.2s'
          }} onMouseEnter={(e) => e.target.style.color = 'var(--text)'}
             onMouseLeave={(e) => e.target.style.color = 'var(--text-secondary)'}>
            Workflow
          </a>
          
          {/* Theme Toggle
          <button
            onClick={toggleTheme}
            style={{
              background: theme === 'dark' ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.05)',
              border: '1px solid var(--border)',
              borderRadius: '10px',
              padding: '0.5rem',
              cursor: 'pointer',
              color: 'var(--text)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.2s'
            }}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          */}
          
          <button className="btn btn-primary" style={{ padding: '0.625rem 1.25rem', fontSize: '0.875rem' }}>
            Get Started
          </button>
        </div>

        {/* Mobile Controls */}
        <div className="mobile-controls">
          {/* 
          <button
            onClick={toggleTheme}
            style={{
              background: theme === 'dark' ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.05)',
              border: '1px solid var(--border)',
              borderRadius: '10px',
              padding: '0.625rem',
              cursor: 'pointer',
              color: 'var(--text)'
            }}
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            style={{
              background: theme === 'dark' ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.05)',
              border: '1px solid var(--border)',
              borderRadius: '10px',
              padding: '0.625rem',
              cursor: 'pointer',
              color: 'var(--text)'
            }}
          >
            {mobileMenuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </div>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          right: 0,
          background: theme === 'dark' ? 'rgba(17, 17, 24, 0.98)' : 'rgba(255, 255, 255, 0.98)',
          backdropFilter: 'blur(16px)',
          borderBottom: '1px solid var(--border)',
          padding: '1.5rem'
        }} className="mobile-menu">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <a href="#features" onClick={() => setMobileMenuOpen(false)} style={{
              color: 'var(--text)',
              fontWeight: 500,
              padding: '0.75rem 1rem',
              textDecoration: 'none',
              borderRadius: '8px'
            }}>Features</a>
            <a href="#workflow" onClick={() => setMobileMenuOpen(false)} style={{
              color: 'var(--text)',
              fontWeight: 500,
              padding: '0.75rem 1rem',
              textDecoration: 'none',
              borderRadius: '8px'
            }}>Workflow</a>
            <div style={{ height: '1rem' }} />
            <button className="btn btn-primary" style={{ width: '100%' }}>
              Get Started
            </button>
          </div>
        </div>
      )}


    </nav>
  );
}
