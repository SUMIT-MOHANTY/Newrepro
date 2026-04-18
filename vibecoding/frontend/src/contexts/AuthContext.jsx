import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

// Vibecoding backend routes are mounted under `/vibecoding/api/*`
// (can be overridden via VITE_API_BASE_URL)
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/vibecoding';

const AuthContext = createContext(null);

function _stripHandoffParam() {
  const url = new URL(window.location.href);
  if (url.searchParams.has('handoff_token')) {
    url.searchParams.delete('handoff_token');
    window.history.replaceState({}, '', url.pathname + url.search + url.hash);
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('vibecoding_token'));
  const [loading, setLoading] = useState(true);

  // Configure axios defaults when token changes
  useEffect(() => {
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      delete axios.defaults.headers.common['Authorization'];
    }
  }, [token]);

  // SSO handoff: exchange BRDAnalyzer handoff_token for a Vibecoding JWT
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const handoffToken = params.get('handoff_token');
    if (!handoffToken) return;

    let cancelled = false;

    const exchangeHandoff = async () => {
      try {
        const res = await axios.post(`${API_BASE_URL}/api/auth/sso`, {
          handoff_token: handoffToken,
        });
        if (cancelled) return;
        const { token: newToken, user: userData } = res.data;
        localStorage.setItem('vibecoding_token', newToken);
        setToken(newToken);
        setUser(userData);
      } catch (err) {
        console.error('SSO handoff failed:', err);
      } finally {
        if (!cancelled) {
          _stripHandoffParam();
          setLoading(false);
        }
      }
    };

    exchangeHandoff();
    return () => { cancelled = true; };
  }, []);

  // Verify existing token on mount (skip if handoff is in progress)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has('handoff_token')) return;

    // Safety timeout — never leave the app stuck on the loading screen
    const safetyTimer = setTimeout(() => setLoading(false), 6000);

    const verifyToken = async () => {
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const response = await axios.get(`${API_BASE_URL}/api/auth/verify`, {
          headers: { Authorization: `Bearer ${token}` },
          timeout: 8000,
        });
        setUser(response.data.user);
      } catch (error) {
        // Token invalid, expired, or backend unreachable — clear and continue
        localStorage.removeItem('vibecoding_token');
        setToken(null);
        setUser(null);
      } finally {
        clearTimeout(safetyTimer);
        setLoading(false);
      }
    };

    verifyToken();
    return () => clearTimeout(safetyTimer);
  }, []);

  const login = useCallback(async (email, password) => {
    const response = await axios.post(`${API_BASE_URL}/api/auth/login`, {
      email,
      password,
    });

    const { token: newToken, user: userData } = response.data;
    localStorage.setItem('vibecoding_token', newToken);
    setToken(newToken);
    setUser(userData);
    return response.data;
  }, []);

  const signup = useCallback(async (username, email, password, fullName) => {
    const response = await axios.post(`${API_BASE_URL}/api/auth/signup`, {
      username,
      email,
      password,
      full_name: fullName || username,
    });

    // Only auto-login if user provided their own password
    // If passwordless (password not provided), user must check email and login manually
    if (password) {
      const { token: newToken, user: userData } = response.data;
      localStorage.setItem('vibecoding_token', newToken);
      setToken(newToken);
      setUser(userData);
    }

    return response.data;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('vibecoding_token');
    setToken(null);
    setUser(null);
  }, []);

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!user,
    login,
    signup,
    logout,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;
