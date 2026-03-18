import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const AuthContext = createContext(null);

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

  // Verify token on mount
  useEffect(() => {
    const verifyToken = async () => {
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const response = await axios.get(`${API_BASE_URL}/api/auth/verify`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setUser(response.data.user);
      } catch (error) {
        // Token is invalid/expired
        localStorage.removeItem('vibecoding_token');
        setToken(null);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    verifyToken();
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
