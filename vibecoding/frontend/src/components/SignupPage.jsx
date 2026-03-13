import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Zap, Eye, EyeOff, ArrowRight, Sparkles, Mail, Lock, User, UserCircle, Check } from 'lucide-react';

export default function SignupPage({ onSwitchToLogin }) {
  const { signup } = useAuth();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [focusedField, setFocusedField] = useState(null);

  // Password strength
  const getPasswordStrength = (pwd) => {
    let score = 0;
    if (pwd.length >= 6) score++;
    if (pwd.length >= 10) score++;
    if (/[A-Z]/.test(pwd)) score++;
    if (/[0-9]/.test(pwd)) score++;
    if (/[^A-Za-z0-9]/.test(pwd)) score++;
    return score;
  };

  const passwordStrength = getPasswordStrength(password);
  const strengthLabels = ['', 'Weak', 'Fair', 'Good', 'Strong', 'Excellent'];
  const strengthColors = ['', '#EF4444', '#F59E0B', '#3B82F6', '#10B981', '#8B5CF6'];

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!username.trim() || !email.trim() || !password.trim()) {
      setError('Please fill in all required fields');
      return;
    }
    if (username.length < 3) {
      setError('Username must be at least 3 characters');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setLoading(true);

    try {
      await signup(username, email, password, fullName);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Signup failed. Please try again.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      {/* Animated Background */}
      <div className="auth-bg">
        <div className="auth-bg-gradient-1 auth-bg-gradient-signup" />
        <div className="auth-bg-gradient-2" />
        <div className="auth-bg-gradient-3" />
        <div className="auth-bg-grid" />
        {[...Array(6)].map((_, i) => (
          <div key={i} className={`auth-particle auth-particle-${i + 1}`} />
        ))}
      </div>

      <div className="auth-container">
        {/* Left Panel - Branding */}
        <div className="auth-branding auth-branding-signup">
          <div className="auth-branding-content">
            <div className="auth-logo-group">
              <div className="auth-logo">
                <Zap className="auth-logo-icon" />
              </div>
              <h1 className="auth-title">VibeCoding</h1>
            </div>
            <p className="auth-tagline">
              Your AI-powered workspace to build, preview, and deploy web applications — all from a single prompt.
            </p>

            {/* How It Works */}
            <div className="auth-how-it-works">
              <span className="auth-section-label">How It Works</span>
              <div className="auth-steps">
                <div className="auth-step">
                  <div className="auth-step-number">1</div>
                  <div>
                    <h4>Describe</h4>
                    <p>Tell the AI what you want to build in plain language</p>
                  </div>
                </div>
                <div className="auth-step">
                  <div className="auth-step-number">2</div>
                  <div>
                    <h4>Generate</h4>
                    <p>Get production-ready code with live preview instantly</p>
                  </div>
                </div>
                <div className="auth-step">
                  <div className="auth-step-number">3</div>
                  <div>
                    <h4>Deploy</h4>
                    <p>Ship your project with one click — no setup needed</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Capabilities */}
            <div className="auth-capabilities">
              <span className="auth-section-label">What You Can Build</span>
              <div className="auth-tech-tags">
                <span className="auth-tech-tag">Landing Pages</span>
                <span className="auth-tech-tag">Dashboards</span>
                <span className="auth-tech-tag">Web Apps</span>
                <span className="auth-tech-tag">APIs</span>
                <span className="auth-tech-tag">Full-Stack Projects</span>
                <span className="auth-tech-tag">Components</span>
              </div>
            </div>
          </div>
          <div className="auth-branding-footer">
            <span>© 2026 Bourtec Solutions</span>
          </div>
        </div>

        {/* Right Panel - Signup Form */}
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
              <h2>Create your account</h2>
              <p>Start building amazing apps in minutes</p>
            </div>

            {error && (
              <div className="auth-error" role="alert">
                <div className="auth-error-dot" />
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="auth-form">
              <div className="auth-form-row">
                <div className={`auth-input-group ${focusedField === 'username' ? 'focused' : ''} ${username ? 'has-value' : ''}`}>
                  <User className="auth-input-icon" size={18} />
                  <input
                    id="signup-username"
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                    onFocus={() => setFocusedField('username')}
                    onBlur={() => setFocusedField(null)}
                    placeholder="Choose a username"
                    autoComplete="username"
                    required
                  />
                  <label htmlFor="signup-username">Username</label>
                </div>

                <div className={`auth-input-group ${focusedField === 'fullname' ? 'focused' : ''} ${fullName ? 'has-value' : ''}`}>
                  <UserCircle className="auth-input-icon" size={18} />
                  <input
                    id="signup-fullname"
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    onFocus={() => setFocusedField('fullname')}
                    onBlur={() => setFocusedField(null)}
                    placeholder="Your full name"
                    autoComplete="name"
                  />
                  <label htmlFor="signup-fullname">Full Name (optional)</label>
                </div>
              </div>

              <div className={`auth-input-group ${focusedField === 'email' ? 'focused' : ''} ${email ? 'has-value' : ''}`}>
                <Mail className="auth-input-icon" size={18} />
                <input
                  id="signup-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onFocus={() => setFocusedField('email')}
                  onBlur={() => setFocusedField(null)}
                  placeholder="Enter your email"
                  autoComplete="email"
                  required
                />
                <label htmlFor="signup-email">Email address</label>
              </div>

              <div className={`auth-input-group ${focusedField === 'password' ? 'focused' : ''} ${password ? 'has-value' : ''}`}>
                <Lock className="auth-input-icon" size={18} />
                <input
                  id="signup-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={() => setFocusedField('password')}
                  onBlur={() => setFocusedField(null)}
                  placeholder="Create a password"
                  autoComplete="new-password"
                  required
                />
                <label htmlFor="signup-password">Password</label>
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

              {/* Password Strength Bar */}
              {password && (
                <div className="auth-password-strength">
                  <div className="auth-strength-bars">
                    {[1, 2, 3, 4, 5].map((level) => (
                      <div
                        key={level}
                        className="auth-strength-bar"
                        style={{
                          backgroundColor: passwordStrength >= level ? strengthColors[passwordStrength] : 'rgba(255,255,255,0.1)',
                        }}
                      />
                    ))}
                  </div>
                  <span className="auth-strength-label" style={{ color: strengthColors[passwordStrength] }}>
                    {strengthLabels[passwordStrength]}
                  </span>
                </div>
              )}

              <div className={`auth-input-group ${focusedField === 'confirm' ? 'focused' : ''} ${confirmPassword ? 'has-value' : ''}`}>
                <Lock className="auth-input-icon" size={18} />
                <input
                  id="signup-confirm"
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  onFocus={() => setFocusedField('confirm')}
                  onBlur={() => setFocusedField(null)}
                  placeholder="Confirm your password"
                  autoComplete="new-password"
                  required
                />
                <label htmlFor="signup-confirm">Confirm Password</label>
                {confirmPassword && password === confirmPassword && (
                  <div className="auth-match-check">
                    <Check size={16} />
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={loading}
                className="auth-submit-btn auth-submit-signup"
                id="signup-submit"
              >
                {loading ? (
                  <div className="auth-spinner" />
                ) : (
                  <>
                    Create Account
                    <Sparkles size={18} />
                  </>
                )}
              </button>
            </form>

            <div className="auth-divider">
              <span>Already have an account?</span>
            </div>

            <button
              onClick={onSwitchToLogin}
              className="auth-switch-btn"
              id="switch-to-login"
            >
              Sign in instead
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
