import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Zap, ArrowRight, Sparkles, Mail, User, UserCircle, Check } from 'lucide-react';

export default function SignupPage({ onSwitchToLogin }) {
  const { signup } = useAuth();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [focusedField, setFocusedField] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess(false);

    if (!username.trim() || !email.trim()) {
      setError('Please fill in all required fields');
      return;
    }
    if (username.length < 3) {
      setError('Username must be at least 3 characters');
      return;
    }

    setLoading(true);

    try {
      // Always passwordless - password will be generated and emailed
      await signup(username, email, undefined, fullName);
      
      // Show success message
      setSuccess(true);
      
      // Redirect to login after 3 seconds
      setTimeout(() => {
        onSwitchToLogin();
      }, 3000);
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

            {success && (
              <div className="auth-success" role="alert">
                <Check className="auth-success-icon" size={20} />
                <div>
                  <strong>Account created successfully!</strong>
                  <p>Check your email for your password. Redirecting to login...</p>
                </div>
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

              {/* Passwordless Info */}
              <div className="auth-passwordless-info">
                <Mail size={16} />
                <span>Your password will be sent to your email</span>
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
