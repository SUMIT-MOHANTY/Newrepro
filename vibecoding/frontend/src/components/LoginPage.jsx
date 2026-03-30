import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Zap, Eye, EyeOff, ArrowRight, Sparkles, Mail, Lock } from 'lucide-react';

export default function LoginPage({ onSwitchToSignup, onForgotPassword }) {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [focusedField, setFocusedField] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError('Please fill in all fields');
      return;
    }
    
    setLoading(true);
    setError('');
    
    try {
      await login(email, password);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Login failed. Please try again.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      {/* Animated Background */}
      <div className="auth-bg">
        <div className="auth-bg-gradient-1" />
        <div className="auth-bg-gradient-2" />
        <div className="auth-bg-gradient-3" />
        <div className="auth-bg-grid" />
        {/* Floating Particles */}
        {[...Array(6)].map((_, i) => (
          <div key={i} className={`auth-particle auth-particle-${i + 1}`} />
        ))}
      </div>

      <div className="auth-container">
        {/* Left Panel - Branding */}
        <div className="auth-branding">
          <div className="auth-branding-content">
            <div className="auth-logo-group">
              <div className="auth-logo">
                <Zap className="auth-logo-icon" />
              </div>
              <h1 className="auth-title">VibeCoding</h1>
            </div>
            <p className="auth-tagline">
              Build stunning web apps with AI-powered code generation
            </p>
            <div className="auth-features">
              <div className="auth-feature">
                <div className="auth-feature-icon">
                  <Sparkles size={18} />
                </div>
                <div>
                  <h4>AI-Powered Generation</h4>
                  <p>Describe what you want, get production-ready code</p>
                </div>
              </div>
              <div className="auth-feature">
                <div className="auth-feature-icon">
                  <Zap size={18} />
                </div>
                <div>
                  <h4>Instant Preview</h4>
                  <p>See your changes in real-time with live preview</p>
                </div>
              </div>
              <div className="auth-feature">
                <div className="auth-feature-icon">
                  <ArrowRight size={18} />
                </div>
                <div>
                  <h4>One-Click Deploy</h4>
                  <p>Ship to production with a single click</p>
                </div>
              </div>
            </div>
          </div>
          <div className="auth-branding-footer">
            <span>© 2026 Bourtec Solutions</span>
          </div>
        </div>

        {/* Right Panel - Login Form */}
        <div className="auth-form-panel">
          <div className="auth-form-wrapper">
            {/* Mobile Logo */}
            <div className="auth-mobile-logo">
              <div className="auth-logo auth-logo-small">
                <Zap size={20} />
              </div>
              <span className="auth-mobile-title">VibeCoding</span>
            </div>

            <div className="auth-form-header">
              <h2>Welcome back</h2>
              <p>Sign in to your account to continue building</p>
            </div>

            {error && (
              <div className="auth-error" role="alert">
                <div className="auth-error-dot" />
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="auth-form">
              <div className={`auth-input-group ${focusedField === 'email' ? 'focused' : ''} ${email ? 'has-value' : ''}`}>
                <Mail className="auth-input-icon" size={18} />
                <input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onFocus={() => setFocusedField('email')}
                  onBlur={() => setFocusedField(null)}
                  placeholder="Enter your email"
                  autoComplete="email"
                  required
                />
                <label htmlFor="login-email">Email address</label>
              </div>

              <div className={`auth-input-group ${focusedField === 'password' ? 'focused' : ''} ${password ? 'has-value' : ''}`}>
                <Lock className="auth-input-icon" size={18} />
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={() => setFocusedField('password')}
                  onBlur={() => setFocusedField(null)}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  required
                />
                <label htmlFor="login-password">Password</label>
                <button
                  type="button"
                  className="auth-password-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="auth-submit-btn"
                id="login-submit"
              >
                {loading ? (
                  <div className="auth-spinner" />
                ) : (
                  <>
                    Sign In
                    <ArrowRight size={18} />
                  </>
                )}
              </button>

              <div className="auth-forgot-password">
                <button 
                  type="button"
                  onClick={onForgotPassword}
                  className="auth-forgot-link"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                >
                  Forgot password?
                </button>
              </div>
            </form>

            <div className="auth-divider">
              <span>New to VibeCoding?</span>
            </div>

            <button 
              onClick={onSwitchToSignup}
              className="auth-switch-btn"
              id="switch-to-signup"
            >
              Create an account
              <Sparkles size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
