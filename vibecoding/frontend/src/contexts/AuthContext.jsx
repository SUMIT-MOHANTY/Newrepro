// AuthContext.jsx — FIXED logout loop
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/vibecoding';
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]   = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('vibecoding_token'));
  const [loading, setLoading] = useState(true);

  // Capture the token that existed when the app first loaded.
  // We only want to *verify* this one token (a stored session from a previous visit).
  // After a fresh login the server already confirmed the token is valid, so we
  // must NOT re-run verification — that's what was causing the logout loop.
  const initialTokenRef = useRef(token);

  // ── Axios default header ─────────────────────────────────────────────────────
  // Keep the Authorization header in sync whenever the token changes (login/logout).
  useEffect(() => {
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      delete axios.defaults.headers.common['Authorization'];
    }
  }, [token]);

  // ── SSO handoff ──────────────────────────────────────────────────────────────
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

        const { token: newToken, user: userData, project } = res.data;
        localStorage.setItem('vibecoding_token', newToken);
        setToken(newToken);
        setUser(userData);

        if (project?.project_id) {
          sessionStorage.setItem('vibe_auto_execute_project', project.project_id);
          sessionStorage.setItem('vibe_auto_execute_token', newToken);
          window.location.href = `/vibecoding/a/${project.project_id}`;
        }
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
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── ONE-TIME token verification on mount ─────────────────────────────────────
  //
  // ⚠️  THE BUG THAT WAS HERE:
  //   The previous effect had [token] as a dependency. That means every call to
  //   setToken() — including the one inside login() — would re-trigger this effect.
  //   If the server happened to return 401 on that second verify (race condition,
  //   brief server hiccup, etc.), setToken(null) was called immediately after a
  //   successful login, logging the user right back out.
  //
  // ✅  THE FIX:
  //   Run verification exactly ONCE on mount, using only the token that was already
  //   in localStorage (a session carried over from a previous visit).
  //   After a fresh login we already have the user object from the login response —
  //   there is nothing to re-verify.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has('handoff_token')) return; // SSO handles its own loading state

    const storedToken = initialTokenRef.current;

    if (!storedToken) {
      setLoading(false);
      return;
    }

    // Safety net: never stay stuck on the loading screen
    const safetyTimer = setTimeout(() => setLoading(false), 6000);

    const verifyStoredToken = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/api/auth/verify`, {
          headers: { Authorization: `Bearer ${storedToken}` },
          timeout: 8000,
        });
        setUser(response.data.user);
      } catch (error) {
        console.error(
          'Stored token is invalid or expired — clearing session:',
          error.response?.data || error.message,
        );
        localStorage.removeItem('vibecoding_token');
        setToken(null);
        setUser(null);
      } finally {
        clearTimeout(safetyTimer);
        setLoading(false);
      }
    };

    verifyStoredToken();
    return () => clearTimeout(safetyTimer);
  }, []); // ← empty deps: runs only once on mount, never after login/logout

  // ── Auth actions ─────────────────────────────────────────────────────────────

  const login = useCallback(async (email, password) => {
    const response = await axios.post(`${API_BASE_URL}/api/auth/login`, { email, password });
    const { token: newToken, user: userData } = response.data;
    localStorage.setItem('vibecoding_token', newToken);
    setToken(newToken);  // updates axios header via the effect above
    setUser(userData);   // marks the user as authenticated immediately
    // No need to call /verify — the login endpoint already validated credentials.
    return response.data;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('vibecoding_token');
    setToken(null);
    setUser(null);
    delete axios.defaults.headers.common['Authorization'];
  }, []);

  const refreshToken = useCallback(async () => {
    try {
      const currentToken = localStorage.getItem('vibecoding_token');
      if (!currentToken) return false;

      const response = await axios.post(`${API_BASE_URL}/api/auth/refresh`, {}, {
        headers: { Authorization: `Bearer ${currentToken}` },
      });

      if (response.data.token) {
        localStorage.setItem('vibecoding_token', response.data.token);
        // Update state + axios header WITHOUT triggering a verify loop
        setToken(response.data.token);
        return true;
      }
      return false;
    } catch (error) {
      console.error('Token refresh failed:', error);
      return false;
    }
  }, []);

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!user,
    login,
    signup: useCallback(async (username, email, password, fullName) => {
      // ... signup logic
    }, []),
    logout,
    refreshToken,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}