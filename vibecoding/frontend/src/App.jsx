import React, { useState, useEffect, useRef, useMemo } from 'react';
import axios from 'axios';
import { Send, Sparkles, Code, Eye, Download, Copy, Check, Zap, RefreshCw, File, Folder, ChevronRight, ChevronDown, Plus, History, LogOut, X, Lock, Unlock } from 'lucide-react';
import { Routes, Route, Navigate, useNavigate, Link, useParams, useLocation } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import LandingPage from './components/LandingPage';
import LoginPage from './components/LoginPage';
import SignupPage from './components/SignupPage';
import ForgotPasswordPage from './components/ForgotPasswordPage';
import ResetPasswordPage from './components/ResetPasswordPage';
import Header from './components/Header';
import GitPanel from './components/GitPanel';
import bourntecLogo from '../assets/bourntec_logo.png';
import { Button } from '@/components/ui/button';
import ChatPanel from './components/ChatPanel';
import FileTree from './components/FileTree';
import CodePreview from './components/CodePreview';
import { useTaskHandlers } from './hooks/useTaskHandlers';
import { useWebSocket } from './hooks/useWebSocket';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/vibecoding';

function App() {
  const { user, isAuthenticated, loading: authLoading, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Global auth token interceptor
  React.useEffect(() => {
    const interceptorId = axios.interceptors.request.use((config) => {
      const token = localStorage.getItem('vibecoding_token');
      if (token && !config.headers['Authorization']) {
        config.headers['Authorization'] = `Bearer ${token}`;
      }
      return config;
    }, (error) => Promise.reject(error));

    return () => {
      axios.interceptors.request.eject(interceptorId);
    };
  }, []);

  // Auth loading state
  if (authLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#0A0A0F]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center animate-pulse">
            <Zap className="w-7 h-7 text-white" />
          </div>
          <div className="auth-spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
        </div>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/" element={
        isAuthenticated ? <Workspace key="default" user={user} logout={logout} isAuthenticated={isAuthenticated} /> :
          <LandingPage onGetStarted={() => navigate('/signup')} onSignIn={() => navigate('/login')} />
      } />
      <Route path="/a/:project_id" element={
        isAuthenticated ? <Workspace key={location.pathname} user={user} logout={logout} isAuthenticated={isAuthenticated} /> :
          <Navigate to="/login" replace />
      } />
      <Route path="/login" element={
        isAuthenticated ? <Navigate to="/" replace /> : <AuthLayout><LoginPage onSwitchToSignup={() => navigate('/signup')} onForgotPassword={() => navigate('/forgot-password')} /></AuthLayout>
      } />
      <Route path="/signup" element={
        isAuthenticated ? <Navigate to="/" replace /> : <AuthLayout><SignupPage onSwitchToLogin={() => navigate('/login')} /></AuthLayout>
      } />
      <Route path="/forgot-password" element={
        isAuthenticated ? <Navigate to="/" replace /> : <AuthLayout><ForgotPasswordPage onBackToLogin={() => navigate('/login')} /></AuthLayout>
      } />
      <Route path="/reset-password" element={
        isAuthenticated ? <Navigate to="/" replace /> : <AuthLayout><ResetPasswordPage /></AuthLayout>
      } />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function AuthLayout({ children }) {
  return (
    <div className="h-screen flex flex-col bg-[#0A0A0F] text-white">
      <Header chatVersion="1.0" user={null} />
      {children}
    </div>
  );
}

function Workspace({ user, logout, isAuthenticated }) {
  // Router hooks must come first
  const { project_id: urlParamId } = useParams();
  const navigate = useNavigate();

  // Refs
  const iframeRef = useRef(null);
  const iframeContainerRef = useRef(null);
  const prevProjectIdRef = useRef(null);
  const containerLoadExpectedRef = useRef(false);
  const containerPollIntervalRef = useRef(null);
  const workspacePollIntervalRef = useRef(null);
  const lastWorkspaceHashRef = useRef('');

  // Determine active project ID from URL
  const params = new URLSearchParams(window.location.search);
  const urlProjectId = urlParamId || params.get('project_id');

  // Initialize prevProjectIdRef
  if (prevProjectIdRef.current === null) {
    prevProjectIdRef.current = urlProjectId;
  }

  // State declarations
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showProjectDropdown, setShowProjectDropdown] = useState(false);
  const [showChatHistory, setShowChatHistory] = useState(false);
  const [showGitPanel, setShowGitPanel] = useState(false);
  const [projects, setProjects] = useState([]);
  const [allChats, setAllChats] = useState([]);
  const [currentProjectId, setCurrentProjectId] = useState(urlProjectId || null);
  const [chatVersion, setChatVersion] = useState(1);
  const [messages, setMessages] = useState([]);
  const [lastMessageId, setLastMessageId] = useState(null);
  const [verificationStatus, setVerificationStatus] = useState(null);
  const [verificationDetails, setVerificationDetails] = useState(null);
  const [branches, setBranches] = useState([]);
  const [currentBranch, setCurrentBranch] = useState('main');
  const [branchCommits, setBranchCommits] = useState([]);
  const [versionsLoaded, setVersionsLoaded] = useState(false);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [viewingCheckpoint, setViewingCheckpoint] = useState(null);
  const [showCheckpointSnackbar, setShowCheckpointSnackbar] = useState(false);
  const [previewCode, setPreviewCode] = useState('');
  const [fullCode, setFullCode] = useState('');
  const [previewUrl, setPreviewUrl] = useState('');
  const [activeView, setActiveView] = useState('preview');
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem('vibecoding_dark_mode');
    return saved !== null ? JSON.parse(saved) : true;
  });
  const [copied, setCopied] = useState(false);
  const [iframeKey, setIframeKey] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileTree, setFileTree] = useState([]);
  const [expandedFolders, setExpandedFolders] = useState(new Set());
  const [editMode, setEditMode] = useState(false);
  const [selectedElement, setSelectedElement] = useState(null);
  const [hoveredElement, setHoveredElement] = useState(null);
  const [editPrompt, setEditPrompt] = useState('');
  const [screenSize, setScreenSize] = useState('desktop');
  const [isDeploying, setIsDeploying] = useState(false);
  const [deployStatus, setDeployStatus] = useState(null);
  const [errorHeader, setErrorHeader] = useState(null);
  const [showVersionHistory, setShowVersionHistory] = useState(false);
  const [isContainerLoading, setIsContainerLoading] = useState(false);
  const [isCheckpointLoading, setIsCheckpointLoading] = useState(false);
  const [discussMode, setDiscussMode] = useState(false);
  const [frozenFiles, setFrozenFiles] = useState([]);
  const [freezeLoading, setFreezeLoading] = useState(false);
  const [isAutonomousPolling, setIsAutonomousPolling] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [pollCount, setPollCount] = useState(0);

  // WebSocket: real-time updates from the container agent
  const { lastMessage: wsMessage, isConnected: wsConnected } = useWebSocket(currentProjectId);

  useEffect(() => {
    if (!wsMessage) return;

    console.log('[WS] Received message:', wsMessage);

    const { content, type, metadata, code, suggestions, timestamp } = wsMessage;

    // Handle agent messages for real-time chat updates
    if (content) {
      setMessages(prev => {
        let lastBgIndex = -1;
        for (let i = prev.length - 1; i >= 0; i--) {
          const msg = prev[i];
          if (msg?.role === 'user' || (msg?.role === 'assistant' && !msg?.metadata?.is_background_log)) {
            break;
          }
          if (msg?.metadata?.is_background_log) {
            lastBgIndex = i;
            break;
          }
        }

        const newLog = {
          message: content,
          timestamp: timestamp || new Date().toISOString(),
          level: type === 'success' ? 'success' : type === 'error' ? 'error' : 'info'
        };

        if (lastBgIndex !== -1) {
          const lastBg = prev[lastBgIndex];
          const hasRegularMessageAfter = prev.slice(lastBgIndex + 1).some(
            m => m.role === 'assistant' && !m.metadata?.is_background_log
          );

          if (!hasRegularMessageAfter || lastBg.isThinking) {
            const updated = [...prev];
            const existingLogs = lastBg.thinkingLogs || [];
            const isDuplicate = existingLogs.some(
              log => log.message === newLog.message &&
                Math.abs(new Date(log.timestamp) - new Date(newLog.timestamp)) < 1000
            );

            updated[lastBgIndex] = {
              ...lastBg,
              content: lastBg.content || content,
              timestamp: newLog.timestamp,
              suggestions: suggestions || lastBg.suggestions || [],
              metadata: {
                ...lastBg.metadata,
                type: type || 'status',
              },
              thinkingLogs: isDuplicate ? existingLogs : [...existingLogs, newLog],
              isThinking: type !== 'success' && type !== 'error',
            };
            return updated;
          }
        }

        const newMsg = {
          id: `ws_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
          role: 'assistant',
          content,
          code: code || null,
          suggestions: suggestions || [],
          timestamp: newLog.timestamp,
          metadata: {
            ...(metadata || {}),
            type: type || 'status',
            is_background_log: true,
          },
          thinkingLogs: [newLog],
          isThinking: type !== 'success' && type !== 'error',
        };

        const lastMsg = prev[prev.length - 1];
        if (lastMsg?.content === content && lastMsg?.role === 'assistant') return prev;

        return [...prev, newMsg];
      });
    }

    // Stop the loading/polling spinner on terminal signals
    const terminalTypes = ['success', 'error', 'celebration', 'task_breakdown'];
    const isTerminal =
      terminalTypes.includes(type) ||
      content?.includes('[AGENT] VERIFICATION') ||
      content?.includes('Changes applied') ||
      content?.includes('Deployment error') ||
      content?.includes('Could not fix syntax errors in') ||
      metadata?.type === 'task_breakdown' ||
      metadata?.task_plan;

    if (isTerminal) {
      console.log('[WS] Terminal signal detected, stopping loader');
      setLoading(false);
      setIsAutonomousPolling(false);
      setTimeout(() => fetchMessages(), 1000);
    }

    // Refresh file tree whenever agent signals a code update
    if (content?.includes('[AGENT] CODE_UPDATE') || type === 'code_update') {
      console.log('[WS] Code update detected, refreshing file tree');
      fetchProjectFiles();
    }

    // Bounce the preview iframe when a new deployment lands
    if (content?.includes('Your app is live') ||
      content?.includes('') ||
      type === 'celebration') {
      console.log('[WS] Deployment complete, refreshing preview');
      setIframeKey(k => k + 1);
    }
  }, [wsMessage]);

  // Task execution handlers
  const { executingTaskId, handleExecuteTask, handleExecuteAllTasks, handleEditTask } = useTaskHandlers(
    currentProjectId,
    messages,
    setMessages,
    setLoading,
    setVerificationStatus
  );

  // Processed messages
  const processedMessages = useMemo(() => {
    return messages.map(msg => {
      if (msg.metadata?.is_background_log && msg.thinkingLogs?.length > 0) {
        return {
          ...msg,
          metadata: {
            ...msg.metadata,
            type: 'background_execution',
            grouped: true,
          }
        };
      }
      return msg;
    });
  }, [messages]);

  useEffect(() => {
    prevProjectIdRef.current = currentProjectId;
  }, [currentProjectId]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (containerPollIntervalRef.current) {
        clearInterval(containerPollIntervalRef.current);
      }
      if (workspacePollIntervalRef.current) {
        clearInterval(workspacePollIntervalRef.current);
      }
    };
  }, []);

  // Fetch messages function placeholder
  const fetchMessages = async () => {
    // Implementation would go here
    console.log('Fetching messages...');
  };

  // Fetch project files function placeholder
  const fetchProjectFiles = async () => {
    // Implementation would go here
    console.log('Fetching project files...');
  };

  return (
    <div className="h-screen flex flex-col bg-[#0A0A0F] text-white overflow-hidden">
      <Header 
        chatVersion={chatVersion} 
        user={user} 
        showUserMenu={showUserMenu}
        setShowUserMenu={setShowUserMenu}
        onNewChat={() => setMessages([])}
        onGitClick={() => setShowGitPanel(true)}
        onDeploy={() => setIsDeploying(true)}
      />
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col">
          <ChatPanel 
            messages={processedMessages}
            loading={loading}
            input={input}
            setInput={setInput}
            onSend={() => {}}
            darkMode={darkMode}
          />
        </div>
        <div className="w-80 border-l border-gray-800 flex flex-col">
          <FileTree 
            code={fileTree}
            darkMode={darkMode}
            onFileSelect={setSelectedFile}
            selectedFile={selectedFile}
            projectId={currentProjectId}
          />
        </div>
      </div>
      {showGitPanel && (
        <GitPanel 
          darkMode={darkMode}
          isVisible={showGitPanel}
          onClose={() => setShowGitPanel(false)}
          projectId={currentProjectId}
        />
      )}
    </div>
  );
}

export default App;
