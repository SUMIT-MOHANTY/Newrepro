import { useState, useEffect } from 'react';
import axios from 'axios';
import { Zap, Lock, Eye, EyeOff, Check, AlertCircle } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/vibecoding';

export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [focusedField, setFocusedField] = useState(null);

  useEffect(() => {
    if (!token) {
      setError('Invalid or missing reset token');
    }
  }, [token]);

  const getPasswordStrength = (pwd) => {
    let score = 0;
    if (pwd.length >= 6) score++;
    if (pwd.length >= 10) score++;
    if (/[A-Z]/.test(pwd)) score++;
    if (/[0-9]/.test(pwd)) score++;
    if (/[^A-Za-z0-9]/.test(pwd)) score++;
    return score;
  };

  const passwordStrength = getPasswordStrength(newPassword);
  const strengthLabels = ['', 'Weak', 'Fair', 'Good', 'Strong', 'Excellent'];
  const strengthColors = ['', '#EF4444', '#F59E0B', '#3B82F6', '#10B981', '#8B5CF6'];

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!token) {
      setError('Invalid or missing reset token');
      return;
    }

    if (!newPassword.trim()) {
      setError('Please enter a new password');
      return;
    }

    if (newPassword.length < 6) {
      setError('Password must be at least 6 characters long');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setLoading(true);

    try {
      await axios.post(`${API_BASE_URL}/api/auth/reset-password`, {
        token,
        new_password: newPassword
      });
      
      setSuccess(true);
      
      // Redirect to login after 3 seconds
      setTimeout(() => {
        navigate('/login');
      }, 3000);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to reset password. Please try again.';
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
              Create a new secure password for your account
            </p>
          </div>
          <div className="auth-branding-footer">
            <span>© 2026 Bourtec Solutions</span>
          </div>
        </div>

        {/* Right Panel - Reset Password Form */}
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
              <h2>Reset Password</h2>
              <p>Enter your new password below</p>
            </div>

            {error && !token && (
              <div className="auth-error" role="alert">
                <AlertCircle size={20} />
                <div>
                  <strong>Invalid Reset Link</strong>
                  <p>The reset link is invalid or has expired. Please request a new one.</p>
                </div>
              </div>
            )}

            {error && token && (
              <div className="auth-error" role="alert">
                <div className="auth-error-dot" />
                {error}
              </div>
            )}

            {success && (
              <div className="auth-success" role="alert">
                <Check className="auth-success-icon" size={20} />
                <div>
                  <strong>Password reset successful!</strong>
                  <p>You can now login with your new password. Redirecting...</p>
                </div>
              </div>
            )}

            {!success && token && (
              <form onSubmit={handleSubmit} className="auth-form">
                <div className={`auth-input-group ${focusedField === 'password' ? 'focused' : ''} ${newPassword ? 'has-value' : ''}`}>
                  <Lock className="auth-input-icon" size={18} />
                  <input
                    id="new-password"
                    type={showPassword ? 'text' : 'password'}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    onFocus={() => setFocusedField('password')}
                    onBlur={() => setFocusedField(null)}
                    placeholder="Enter new password"
                    autoComplete="new-password"
                    required
                    disabled={loading}
                  />
                  <label htmlFor="new-password">New Password</label>
                  <button
                    type="button"
                    className="auth-password-toggle"
                    onClick={() => setShowPassword(!showPassword)}
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>

                {newPassword && (
                  <div className="auth-password-strength">
                    <div className="auth-strength-bars">
                      {[1, 2, 3, 4, 5].map((level) => (
                        <div
                          key={level}
                          className="auth-strength-bar"
                          style={{
                            backgroundColor: level <= passwordStrength ? strengthColors[passwordStrength] : 'rgba(255, 255, 255, 0.1)'
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
                    id="confirm-password"
                    type={showConfirmPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    onFocus={() => setFocusedField('confirm')}
                    onBlur={() => setFocusedField(null)}
                    placeholder="Confirm new password"
                    autoComplete="new-password"
                    required
                    disabled={loading}
                  />
                  <label htmlFor="confirm-password">Confirm Password</label>
                  <button
                    type="button"
                    className="auth-password-toggle"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    tabIndex={-1}
                  >
                    {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                  {confirmPassword && newPassword === confirmPassword && (
                    <div className="auth-match-check">
                      <Check size={18} />
                    </div>
                  )}
                </div>

                <button
                  type="submit"
                  disabled={loading || !newPassword || !confirmPassword || newPassword !== confirmPassword}
                  className="auth-submit-btn"
                >
                  {loading ? (
                    <div className="auth-spinner" />
                  ) : (
                    <>
                      Reset Password
                      <Check size={18} />
                    </>
                  )}
                </button>
              </form>
            )}

            {!token && (
              <div className="auth-divider">
                <span>Need a new link?</span>
              </div>
            )}

            <button
              onClick={() => navigate(token ? '/login' : '/forgot-password')}
              className="auth-switch-btn"
            >
              {token ? 'Back to Login' : 'Request New Link'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
