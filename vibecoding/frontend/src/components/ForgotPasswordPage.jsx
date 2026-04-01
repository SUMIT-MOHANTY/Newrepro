import { useState } from 'react';
import axios from 'axios';
import { Zap, Mail, ArrowLeft, Check } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/vibecoding';

export default function ForgotPasswordPage({ onBackToLogin }) {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [focusedField, setFocusedField] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess(false);

    if (!email.trim()) {
      setError('Please enter your email address');
      return;
    }

    setLoading(true);

    try {
      await axios.post(`${API_BASE_URL}/api/auth/forgot-password`, { email });
      setSuccess(true);
      
      // Redirect to login after 5 seconds
      setTimeout(() => {
        onBackToLogin();
      }, 5000);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to process request. Please try again.';
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
              Reset your password and get back to building amazing applications.
            </p>
          </div>
          <div className="auth-branding-footer">
            <span>© 2026 Bourtec Solutions</span>
          </div>
        </div>

        {/* Right Panel - Forgot Password Form */}
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
              <h2>Forgot Password?</h2>
              <p>Enter your email and we'll send you a new password</p>
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
                  <strong>Password reset email sent!</strong>
                  <p>Check your email for your new password. Redirecting to login...</p>
                </div>
              </div>
            )}

            <form onSubmit={handleSubmit} className="auth-form">
              <div className={`auth-input-group ${focusedField === 'email' ? 'focused' : ''} ${email ? 'has-value' : ''}`}>
                <Mail className="auth-input-icon" size={18} />
                <input
                  id="forgot-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onFocus={() => setFocusedField('email')}
                  onBlur={() => setFocusedField(null)}
                  placeholder="Enter your email"
                  autoComplete="email"
                  required
                  disabled={success}
                />
                <label htmlFor="forgot-email">Email address</label>
              </div>

              <button
                type="submit"
                disabled={loading || success}
                className="auth-submit-btn"
                id="forgot-submit"
              >
                {loading ? (
                  <div className="auth-spinner" />
                ) : success ? (
                  <>
                    <Check size={18} />
                    Email Sent
                  </>
                ) : (
                  <>
                    Reset Password
                    <Mail size={18} />
                  </>
                )}
              </button>
            </form>

            <div className="auth-divider">
              <span>Remember your password?</span>
            </div>

            <button
              onClick={onBackToLogin}
              className="auth-switch-btn"
              id="back-to-login"
            >
              <ArrowLeft size={16} />
              Back to Login
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
