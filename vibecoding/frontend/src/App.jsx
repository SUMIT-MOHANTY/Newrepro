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

  // ── Global auth token interceptor ──────────────────────────────────────────
  // Attach the JWT token to every axios request automatically.
  // This fixes the 401 on /api/auth/verify that logged users out on page refresh,
  // because the AuthContext's verify call fired before headers were set manually.
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
  const [verificationStatus, setVerificationStatus] = useState(null); // 'checking', 'completed', 'failed'
  const [verificationDetails, setVerificationDetails] = useState(null);
  const [branches, setBranches] = useState([]);
  const [currentBranch, setCurrentBranch] = useState('main');
  const [branchCommits, setBranchCommits] = useState([]);
  const [versionsLoaded, setVersionsLoaded] = useState(false);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [viewingCheckpoint, setViewingCheckpoint] = useState(null); // {hash, message, date}
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

  // ── WebSocket: real-time updates from the container agent ──────────────────
  const { lastMessage: wsMessage, isConnected: wsConnected } = useWebSocket(currentProjectId);

  /**
   * Handle every inbound WebSocket frame.
   * 
   * The ai-agent.py `report()` function posts to /vibecoding/api/broadcast/{project_id}
   * which calls manager.broadcast() — forwarding the payload to every connected WS client.
   * 
   * Payload shape (from ai-agent.py report()):
   *   { content, type, summary, metadata, timestamp, code, suggestions }
   */
  // IN App.jsx — REPLACE the entire WS useEffect with this:

  useEffect(() => {
    if (!wsMessage) return;

    console.log('[WS] Received message:', wsMessage);

    const { content, type, metadata, code, suggestions, timestamp } = wsMessage;

    // ── 1. Handle agent messages for real-time chat updates ───────────────────
    if (content) {
      setMessages(prev => {
        // Find the most recent background log message in the array
        // (not just the last one — there might be regular messages after it)
        let lastBgIndex = -1;
        for (let i = prev.length - 1; i >= 0; i--) {
          if (prev[i]?.metadata?.is_background_log && !prev[i]?.metadata?.grouped) {
            lastBgIndex = i;
            break;
          }
        }

        const newLog = {
          message: content,
          timestamp: timestamp || new Date().toISOString(),
          level: type === 'success' ? 'success' : type === 'error' ? 'error' : 'info'
        };

        // If we found a recent background message AND it's still "thinking", update it
        if (lastBgIndex !== -1) {
          const lastBg = prev[lastBgIndex];
          // Only update if it's still active (thinking) or this is part of same session
          // We determine "same session" by checking if no regular assistant message came after
          const hasRegularMessageAfter = prev.slice(lastBgIndex + 1).some(
            m => m.role === 'assistant' && !m.metadata?.is_background_log
          );
          
          if (!hasRegularMessageAfter || lastBg.isThinking) {
            const updated = [...prev];
            
            // Deduplicate: check if this exact log already exists
            const existingLogs = lastBg.thinkingLogs || [];
            const isDuplicate = existingLogs.some(
              log => log.message === newLog.message && 
                     Math.abs(new Date(log.timestamp) - new Date(newLog.timestamp)) < 1000 // within 1 second
            );
            
            updated[lastBgIndex] = {
              ...lastBg,
              content: lastBg.content || content, // Keep original content, don't replace
              timestamp: newLog.timestamp,
              metadata: {
                ...lastBg.metadata,
                type: type || 'status',
              },
              thinkingLogs: isDuplicate ? existingLogs : [...existingLogs, newLog], // Append new log only if not duplicate
              isThinking: type !== 'success' && type !== 'error',
            };
            return updated;
          }
        }

        // No suitable background message found — create a new one
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

        // Deduplicate: skip if the last message has identical content
        const lastMsg = prev[prev.length - 1];
        if (lastMsg?.content === content && lastMsg?.role === 'assistant') return prev;
        
        return [...prev, newMsg];
      });
    }

    // ── 2. Stop the loading/polling spinner on terminal signals ───────────────
    const terminalTypes = ['success', 'error', 'celebration', 'task_breakdown'];
    const isTerminal =
      terminalTypes.includes(type) ||
      content?.includes('[AGENT] VERIFICATION') ||
      content?.includes('✅ Changes applied') ||
      content?.includes('Deployment error') ||
      metadata?.type === 'task_breakdown' ||
      metadata?.task_plan;

    if (isTerminal) {
      console.log('[WS] Terminal signal detected, stopping loader');
      setLoading(false);
      setIsAutonomousPolling(false);
      // Do a final DB sync after a short delay to get the fully-persisted,
      // properly-grouped messages (with isThinking:false, collapsed ThinkingBlock).
      setTimeout(() => fetchMessages(), 1000);
    }

    // ── 3. Refresh file tree whenever agent signals a code update ─────────────
    if (content?.includes('[AGENT] CODE_UPDATE') || type === 'code_update') {
      console.log('[WS] Code update detected, refreshing file tree');
      fetchProjectFiles();
    }

    // ── 4. Bounce the preview iframe when a new deployment lands ─────────────
    if (content?.includes('Your app is live') ||
        content?.includes('🎉') ||
        type === 'celebration') {
      console.log('[WS] Deployment complete, refreshing preview');
      setIframeKey(k => k + 1);
    }
  }, [wsMessage]);
    
  // eslint-disable-line react-hooks/exhaustive-deps

  // Task execution handlers
  const { executingTaskId, handleExecuteTask, handleExecuteAllTasks, handleEditTask } = useTaskHandlers(
    currentProjectId,
    messages,
    setMessages,
    setLoading,
    setVerificationStatus
  );

  // ── processedMessages ───────────────────────────────────────────────────────
  // Normalise messages from two sources:
  //   1. Live WS messages   — created by the WS handler with is_background_log + thinkingLogs
  //   2. DB-loaded messages — already grouped by main.py's _group_log_messages()
  // Both carry is_background_log:true and thinkingLogs[], so the same ChatMessage
  // rendering path applies for both.
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
      stopWorkspacePolling();
      if (containerPollIntervalRef.current) clearTimeout(containerPollIntervalRef.current);
    };
  }, []);

  // Sync dark mode with document and localStorage
  useEffect(() => {
    localStorage.setItem('vibecoding_dark_mode', JSON.stringify(darkMode));
    if (darkMode) {
      document.documentElement.classList.add('dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.setAttribute('data-theme', 'light');
    }
  }, [darkMode]);

  // Fetch messages and frozen files when project changes
  useEffect(() => {
    if (currentProjectId) {
      fetchMessages();
      fetchFrozenFiles();
    }
  }, [currentProjectId]);

  // Polling for verification status
  useEffect(() => {
    if (lastMessageId && verificationStatus === 'checking') {
      const pollVerification = async () => {
        try {
          const token = localStorage.getItem('vibecoding_token');
          const response = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/messages`, {
            headers: { Authorization: `Bearer ${token}` }
          });

          const latestMsg = response.data.messages?.find(m => m.id === lastMessageId);
          if (latestMsg?.metadata?.verification) {
            const v = latestMsg.metadata.verification;
            if (v.status === 'completed') {
              setVerificationStatus('completed');
              setVerificationDetails(v);
              setMessages(response.data.messages); // Sync full data
            } else if (v.status === 'error') {
              setVerificationStatus('failed');
              setVerificationDetails(v);
            }
          }
        } catch (e) {
          console.error('Polling error:', e);
        }
      };

      const interval = setInterval(pollVerification, 2000);
      return () => clearInterval(interval);
    }
  }, [lastMessageId, verificationStatus, currentProjectId]);

  // --- Autonomous Polling Logic ---
  //
  // KEY DESIGN: The polling loop must NEVER blindly overwrite setMessages() with
  // raw DB rows while an agent task is in-flight, because:
  //   - WebSocket messages build up rich thinkingLogs in memory
  //   - Raw DB rows (pre-grouped) have isThinking:false and no thinkingLogs
  //   - Replacing state with DB rows mid-task causes ThinkingBlock to vanish
  //
  // FIX: main.py's _group_log_messages() now marks tail log groups isThinking:true
  // when no terminal message has followed. The polling merges DB messages with the
  // live in-memory state: non-log messages are synced freely; the live thinking
  // group is only replaced when the DB version also has isThinking:true (still
  // in-flight) or when loading has ended.
  useEffect(() => {
    let pollInterval;
    if (isAutonomousPolling && currentProjectId) {
      setPollCount(0);

      pollInterval = setInterval(async () => {
        try {
          setPollCount(prev => prev + 1);
          const token = localStorage.getItem('vibecoding_token');
          const response = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/messages`, {
            headers: { Authorization: `Bearer ${token}` }
          });

          const tasksResponse = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/tasks`, {
            headers: { Authorization: `Bearer ${token}` }
          }).catch(err => {
            console.warn('Failed to fetch tasks during polling:', err);
            return { data: { tasks: [], total_tasks: 0 } };
          });

          if (response.data.messages) {
            let dbMessages = response.data.messages.filter(msg => !msg.metadata?.temporary);

            // ── Inject task plan if tasks exist ─────────────────────────────
            if (tasksResponse.data.tasks && tasksResponse.data.tasks.length > 0) {
              const taskPlan = {
                project_summary: tasksResponse.data.project_summary || 'Task breakdown',
                tasks: tasksResponse.data.tasks,
                total_tasks: tasksResponse.data.total_tasks,
                completed_count: tasksResponse.data.completed_count,
                pending_count: tasksResponse.data.pending_count,
                failed_count: tasksResponse.data.failed_count
              };
              const tIdx = dbMessages.findIndex(msg =>
                msg.metadata?.type === 'task_breakdown' ||
                msg.metadata?.awaiting_task_selection ||
                (msg.content && msg.content.includes('Task Breakdown Complete'))
              );
              if (tIdx !== -1) {
                dbMessages[tIdx] = {
                  ...dbMessages[tIdx],
                  metadata: { ...dbMessages[tIdx].metadata, task_plan: taskPlan }
                };
              } else {
                dbMessages.push({
                  id: `task_breakdown_${Date.now()}`,
                  role: 'assistant',
                  content: `📋 **Task Breakdown Complete!**\n\n${taskPlan.project_summary}\n\nI've broken this down into **${taskPlan.total_tasks} tasks**. You can:\n• Click "Execute All" to start building automatically\n• Click "Execute" on individual tasks to run them one by one\n• Click "Edit" to modify task descriptions before execution\n\nReady to start building?`,
                  timestamp: new Date().toISOString(),
                  metadata: { type: 'task_breakdown', task_plan: taskPlan, awaiting_task_selection: true }
                });
              }
            }

            // ── Check terminal signals ───────────────────────────────────────
            const lastDb = dbMessages[dbMessages.length - 1];

            const isDbTerminal = (
              lastDb?.metadata?.type === 'task_breakdown' ||
              lastDb?.metadata?.task_plan ||
              lastDb?.content?.includes('[AGENT] VERIFICATION') ||
              lastDb?.suggestions?.length > 0 ||
              lastDb?.code
            );

            const hasGotItStop = pollCount >= 5 &&
              dbMessages.some(m => m.role === 'assistant' &&
                (m.content?.includes('Got it!') || m.content?.includes('On it!'))) &&
              tasksResponse.data.total_tasks === 0;

            const isTimedOut = pollCount >= 20;

            if (isDbTerminal || hasGotItStop || isTimedOut) {
              const reason = isDbTerminal ? 'terminal DB signal' : hasGotItStop ? 'got-it + no tasks' : 'timeout';
              console.log(`✅ Stopping polling: ${reason}`);
              setIsAutonomousPolling(false);
              setLoading(false);
              // Safe to do a full sync now — agent is done
              setMessages(dbMessages);
              return;
            }

            // ── Safe merge: preserve live thinkingLogs, sync everything else ──
            // The DB tail group now has isThinking:true (set by main.py fix).
            // We merge it with the in-memory state so thinkingLogs accumulate.
            setMessages(prev => {
              // Find the in-memory live thinking group (isThinking:true)
              const liveIdx = prev.findLastIndex?.(m =>
                m.metadata?.is_background_log && m.isThinking
              ) ?? [...prev].reverse().findIndex(m =>
                m.metadata?.is_background_log && m.isThinking
              );
              const liveMsgIdx = liveIdx >= 0
                ? (prev.findLastIndex
                    ? liveIdx
                    : prev.length - 1 - liveIdx)
                : -1;

              // Find the DB tail thinking group
              const dbTailIdx = dbMessages.findLastIndex?.(m =>
                m.metadata?.is_background_log && m.metadata?.grouped
              ) ?? [...dbMessages].reverse().findIndex(m =>
                m.metadata?.is_background_log && m.metadata?.grouped
              );
              const dbTailMsgIdx = dbTailIdx >= 0
                ? (dbMessages.findLastIndex
                    ? dbTailIdx
                    : dbMessages.length - 1 - dbTailIdx)
                : -1;

              if (liveMsgIdx < 0 || dbTailMsgIdx < 0) {
                // No live thinking group in memory — safe to sync DB directly
                return dbMessages;
              }

              // Merge: use DB as base but keep the live thinkingLogs and isThinking:true
              const liveMsg = prev[liveMsgIdx];
              const dbTailMsg = dbMessages[dbTailMsgIdx];

              // Merge thinkingLogs: DB logs first (deduplicated), then any extra live ones
              const dbLogContents = new Set((dbTailMsg.thinkingLogs || []).map(l => l.message));
              const extraLiveLogs = (liveMsg.thinkingLogs || []).filter(l => !dbLogContents.has(l.message));
              const mergedLogs = [...(dbTailMsg.thinkingLogs || []), ...extraLiveLogs];

              const merged = dbMessages.map((m, i) =>
                i === dbTailMsgIdx
                  ? { ...m, thinkingLogs: mergedLogs, isThinking: true }
                  : m
              );

              return merged;
            });

            if (lastDb?.content?.includes('[AGENT] CODE_UPDATE')) {
              await fetchProjectFiles();
            }

            console.log(`🔄 Poll #${pollCount}: ${dbMessages.length} DB msgs, ${tasksResponse.data.total_tasks} tasks`);
          }
        } catch (e) {
          console.error('Polling error:', e);
          setIsAutonomousPolling(false);
          setLoading(false);
        }
      }, wsConnected ? 5000 : 2000);
    }
    return () => {
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [isAutonomousPolling, currentProjectId, pollCount, wsConnected]);

  const fetchProjectFiles = async () => {
    if (!currentProjectId) return;
    try {
      const filesResp = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/versions/workspace/files`);
      const filesMap = filesResp.data.files || {};
      let rebuiltCode = '';
      Object.entries(filesMap).forEach(([filePath, content]) => {
        rebuiltCode += `// FILE: ${filePath}\n${content}\n\n`;
      });
      setFullCode(rebuiltCode);
      const files = parseCodeToFiles(rebuiltCode);
      setFileTree(files);
    } catch (err) {
      console.error("Tree refresh failed:", err);
    }
  };

  const fetchMessages = async () => {
    if (!currentProjectId) return;
    try {
      const token = localStorage.getItem('vibecoding_token');
      
      // Fetch messages
      const messagesResponse = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/messages`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      // Fetch tasks
      const tasksResponse = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/tasks`, {
        headers: { Authorization: `Bearer ${token}` }
      }).catch(err => {
        console.warn('Failed to fetch tasks:', err);
        return { data: { tasks: [], total_tasks: 0 } };
      });
      
      if (messagesResponse.data.messages) {
        let messages = messagesResponse.data.messages;
        
        // Check if any message signals loading complete
        const hasLoadingComplete = messages.some(msg => 
          msg.metadata?.loading_complete === true ||
          msg.metadata?.type === 'task_breakdown' ||
          msg.metadata?.type === 'task_execution_complete' ||
          msg.metadata?.type === 'task_execution_failed' ||
          msg.metadata?.type === 'task_execution_blocked'
        );
        
        if (hasLoadingComplete) {
          console.log('✅ Loading complete signal detected - stopping loader');
          setLoading(false);
          setIsAutonomousPolling(false);
        }
        
        // If we have tasks, find the task breakdown message and inject the task plan
        if (tasksResponse.data.tasks && tasksResponse.data.tasks.length > 0) {
          const taskPlan = {
            project_summary: tasksResponse.data.project_summary || 'Task breakdown',
            tasks: tasksResponse.data.tasks,
            total_tasks: tasksResponse.data.total_tasks,
            completed_count: tasksResponse.data.completed_count,
            pending_count: tasksResponse.data.pending_count,
            failed_count: tasksResponse.data.failed_count
          };
          
          // Find the most recent message with task breakdown metadata or create one
          const taskBreakdownMsgIndex = messages.findIndex(msg => 
            msg.metadata?.type === 'task_breakdown' || 
            msg.metadata?.awaiting_task_selection ||
            (msg.content && msg.content.includes('Task Breakdown Complete'))
          );
          
          if (taskBreakdownMsgIndex !== -1) {
            // Update existing message with task plan
            messages[taskBreakdownMsgIndex] = {
              ...messages[taskBreakdownMsgIndex],
              metadata: {
                ...messages[taskBreakdownMsgIndex].metadata,
                task_plan: taskPlan
              }
            };
          } else {
            // Create a new task breakdown message if none exists
            const taskBreakdownMsg = {
              id: `task_breakdown_${Date.now()}`,
              role: 'assistant',
              content: `📋 **Task Breakdown Complete!**\n\nI've broken this down into **${taskPlan.total_tasks} tasks**. You can:\n• Click "Execute All" to start building automatically\n• Click "Execute" on individual tasks to run them one by one\n• Click "Edit" to modify task descriptions before execution\n\nReady to start building?`,
              timestamp: new Date().toISOString(),
              metadata: {
                type: 'task_breakdown',
                task_plan: taskPlan,
                awaiting_task_selection: true
              }
            };
            messages.push(taskBreakdownMsg);
          }
        }
        
        setMessages(messages);
      }
    } catch (error) {
      console.error('Failed to fetch messages:', error);
    }
  };

  const fetchFrozenFiles = async () => {
    if (!currentProjectId) return;

    try {
      const token = localStorage.getItem('vibecoding_token');
      const response = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/frozen-files`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setFrozenFiles(response.data.frozen_files || []);
    } catch (error) {
      console.error('Failed to fetch frozen files:', error);
    }
  };

  const toggleFileFrozen = async (filePath, e) => {
    e.stopPropagation();
    if (!currentProjectId) return;

    setFreezeLoading(true);
    try {
      const isFrozen = frozenFiles.includes(filePath);

      await axios.post(`${API_BASE_URL}/api/projects/${currentProjectId}/frozen-files`, {
        file_path: filePath,
        frozen: !isFrozen
      });

      // Update local state
      if (isFrozen) {
        setFrozenFiles(frozenFiles.filter(f => f !== filePath));
      } else {
        setFrozenFiles([...frozenFiles, filePath]);
      }
    } catch (error) {
      console.error('Failed to toggle file frozen status:', error);
    } finally {
      setFreezeLoading(false);
    }
  };

  const fetchProjects = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/projects`, {
        
      });
      // Sort projects by created_at descending (most recent first)
      const sortedProjects = (response.data.projects || []).sort((a, b) => {
        return new Date(b.created_at) - new Date(a.created_at);
      });
      setProjects(sortedProjects);
    } catch (error) {
      console.error('Failed to fetch projects:', error);
    }
  };

  // ── Container health polling ─────────────────────────────────────────────
  // Polls /container-health until the agent's Nginx gateway responds, then
  // flips the iframe to visible. Workspace file polling runs independently.
  const startContainerRetry = (url) => {
    if (containerPollIntervalRef.current) {
      clearTimeout(containerPollIntervalRef.current);
      containerPollIntervalRef.current = null;
    }

    containerLoadExpectedRef.current = true;
    let attempts = 0;
    const maxAttempts = 60;

    const poll = async () => {
      attempts++;
      try {
        const resp = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/container-health`);
        if (resp.data.healthy) {
          console.log(`✅ Container healthy after ${attempts} polls`);
          containerLoadExpectedRef.current = false;
          setIsContainerLoading(false);
          setIframeKey(prev => prev + 1);
          containerPollIntervalRef.current = null;
          return;
        }
        console.log(`🔄 Health poll ${attempts}/${maxAttempts}: ${resp.data.reason || 'not ready'}`);
      } catch (err) {
        console.log(`🔄 Health poll ${attempts}/${maxAttempts}: request failed`);
      }

      if (attempts < maxAttempts) {
        containerPollIntervalRef.current = setTimeout(poll, 2000);
      } else {
        console.log('⏱️ Max health polls reached — showing preview anyway');
        containerLoadExpectedRef.current = false;
        setIsContainerLoading(false);
        setIframeKey(prev => prev + 1);
        containerPollIntervalRef.current = null;
      }
    };

    console.log('🚀 Starting health polling in 3s for:', url);
    containerPollIntervalRef.current = setTimeout(poll, 3000);
  };

  // ── Live workspace file polling ───────────────────────────────────────────
  // Polls the workspace files every 3s while the agent is active.
  // Updates the file tree and code view in real-time as the agent writes files.
  const startWorkspacePolling = (projectId) => {
    stopWorkspacePolling();
    lastWorkspaceHashRef.current = '';
    console.log('📂 Starting live workspace polling for:', projectId);

    const poll = async () => {
      try {
        const resp = await axios.get(`${API_BASE_URL}/api/projects/${projectId}/versions/workspace/files`);
        const filesMap = resp.data.files || {};
        if (Object.keys(filesMap).length === 0) return;

        // Simple hash: sorted file paths + total char count to detect changes
        const hash = Object.keys(filesMap).sort().join('|') + ':' +
          Object.values(filesMap).reduce((acc, c) => acc + c.length, 0);

        if (hash === lastWorkspaceHashRef.current) return; // nothing changed
        lastWorkspaceHashRef.current = hash;

        console.log('📝 Workspace changed — updating file tree live');

        // Rebuild code string with file markers
        let rebuiltCode = '';
        Object.entries(filesMap).forEach(([filePath, content]) => {
          rebuiltCode += `// FILE: ${filePath}\n${content}\n\n`;
        });
        setFullCode(rebuiltCode);

        // Update previewCode with best HTML candidate
        const indexFile = filesMap['index.html'] || filesMap['index.jsx'] || Object.values(filesMap)[0];
        setPreviewCode(indexFile || rebuiltCode);

        // Rebuild file tree
        const files = parseCodeToFiles(rebuiltCode);
        setFileTree(files);

        // Auto-expand all folders
        const allFolderPaths = new Set();
        const collectFolders = (items) => {
          items.forEach(item => {
            if (item.type === 'folder') {
              allFolderPaths.add(item.path);
              if (item.children) collectFolders(item.children);
            }
          });
        };
        collectFolders(files);
        setExpandedFolders(allFolderPaths);

      } catch (err) {
        // Silently ignore — workspace may not exist yet
      }
    };

    workspacePollIntervalRef.current = setInterval(poll, 3000);
  };

  const stopWorkspacePolling = () => {
    if (workspacePollIntervalRef.current) {
      clearInterval(workspacePollIntervalRef.current);
      workspacePollIntervalRef.current = null;
      console.log('📂 Stopped live workspace polling');
    }
  };

  // Load branches from backend for the current project
  const loadBranchesFromBackend = async (projectId) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/projects/${projectId}/versions`);
      const backendBranches = response.data.versions || [];

      if (backendBranches.length > 0) {
        console.log(`📦 Found ${backendBranches.length} branches on backend for project ${projectId}`);

        // Set branches
        setBranches(backendBranches);

        // Find current branch
        const currentBranchData = backendBranches.find(b => b.is_current);
        const currentBranchName = currentBranchData ? currentBranchData.version_id : backendBranches[0].version_id;
        setCurrentBranch(currentBranchName);

        // Load commits for current branch
        await loadBranchCommits(projectId, currentBranchName);

        // Load files for current branch
        try {
          const filesResp = await axios.get(`${API_BASE_URL}/api/projects/${projectId}/versions/${currentBranchName}/files`);
          const filesMap = filesResp.data.files || {};

          // Build code string with file markers
          let fullCode = '';
          Object.entries(filesMap).forEach(([filePath, content]) => {
            fullCode += `// FILE: ${filePath}\n${content}\n\n`;
          });

          // Parse into file tree
          const fileTree = parseCodeToFiles(fullCode);

          setFullCode(fullCode);
          setFileTree(fileTree);

          // Determine best initial preview code (usually index.html)
          const indexFile = filesMap['index.html'] || filesMap['index.jsx'] || Object.values(filesMap)[0];
          setPreviewCode(indexFile || '');

          // Select first file
          const findFirstFile = (items) => {
            for (const item of items) {
              if (item.type === 'file') return item;
              if (item.type === 'folder' && item.children) {
                const found = findFirstFile(item.children);
                if (found) return found;
              }
            }
            return null;
          };
          const firstFile = findFirstFile(fileTree);
          if (firstFile) setSelectedFile(firstFile);

          // Get or create preview URL — retry if Docker is still starting after PC restart
          const startPreviewWithRetry = async (retries = 3, delay = 3000) => {
            for (let attempt = 1; attempt <= retries; attempt++) {
              try {
                const previewResp = await axios.post(`${API_BASE_URL}/api/projects/${projectId}/versions/workspace/preview`);
                if (previewResp.data.preview_url) {
                  console.log(`🌐 Restored container preview (attempt ${attempt}):`, previewResp.data.preview_url);
                  containerLoadExpectedRef.current = true;
                  setIsContainerLoading(true);
                  setPreviewUrl(previewResp.data.preview_url);
                  startContainerRetry(previewResp.data.preview_url);
                  return;
                }
              } catch (previewErr) {
                console.warn(`⚠️ Preview attempt ${attempt}/${retries} failed:`, previewErr.message);
                if (attempt < retries) {
                  await new Promise(r => setTimeout(r, delay));
                }
              }
            }
            console.error('Failed to get preview URL after all retries');
          };
          startPreviewWithRetry();

        } catch (err) {
          console.error('Failed to load branch files:', err);
        }
      }

      setVersionsLoaded(true);
    } catch (err) {
      console.error('Failed to load branches from backend:', err);
      setVersionsLoaded(true);
    }
  };

  // Load commits for a specific branch
  const loadBranchCommits = async (projectId, branchName) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/projects/${projectId}/branches/${branchName}/commits`);
      const commits = response.data.commits || [];
      console.log(`📝 Found ${commits.length} commits in branch ${branchName}`);
      setBranchCommits(commits);
    } catch (err) {
      console.error('Failed to load branch commits:', err);
      setBranchCommits([]);
    }
  };

  useEffect(() => {
    const initProject = async () => {
      const params = new URLSearchParams(window.location.search);
      const urlProjectId = params.get('project_id') || window.location.pathname.split('/a/')[1];
      const projectName = params.get('name');

      let projectIdToLoad = currentProjectId;

      if (urlProjectId) {
        try {
          // First, check if the project exists
          const response = await axios.get(`${API_BASE_URL}/api/projects/${urlProjectId}`, {
            
          });

          // Project exists, load it
          setCurrentProjectId(urlProjectId);
          projectIdToLoad = urlProjectId;

          // Clear URL params without reloading
          window.history.replaceState({}, '', `/vibecoding/a/${urlProjectId}`);

          // Start the container in the background immediately so preview warms up
          // while the user reads their chat history — do NOT switch to preview tab
          try {
            const startResp = await axios.post(
              `${API_BASE_URL}/api/projects/${urlProjectId}/start`,
              {},
              {  }
            );
            if (startResp.data.started && startResp.data.preview_url) {
              console.log('🚀 Container starting for project:', urlProjectId);
              setPreviewUrl(startResp.data.preview_url);
              // Start health polling silently — preview tab will show spinner only when user switches to it
              containerLoadExpectedRef.current = true;
              setIsContainerLoading(true);
              startContainerRetry(startResp.data.preview_url);
              startWorkspacePolling(urlProjectId);
            }
          } catch (startErr) {
            console.warn('Container pre-start failed (non-critical):', startErr.message);
          }
        } catch (error) {
          console.error('Failed to load project from URL:', error);
          // If project doesn't exist (404) or access denied (403), redirect to last opened project or home
          if (error.response && (error.response.status === 404 || error.response.status === 403)) {
            console.warn(`Project ${urlProjectId} not found or access denied`);
            // Redirect to last opened project if available, otherwise to home
            if (currentProjectId) {
              console.log(`Redirecting to last opened project: ${currentProjectId}`);
              navigate(`/vibecoding/a/${currentProjectId}`);
            } else {
              console.log('No last project, redirecting to home');
              navigate('/vibecoding');
            }
            return;
          }
        }
      }

      fetchProjects();

      // Load branches from the backend (this will also restore preview URL)
      await loadBranchesFromBackend(projectIdToLoad);

      // Check for auto-execution flag from D-Suite handoff
      const autoExecuteProjectId = sessionStorage.getItem('vibe_auto_execute_project');
      const autoExecuteToken = sessionStorage.getItem('vibe_auto_execute_token');
      
      if (autoExecuteProjectId && autoExecuteToken && autoExecuteProjectId === projectIdToLoad) {
        console.log('🚀 Auto-execution triggered for project:', autoExecuteProjectId);
        
        // Clear the flags
        sessionStorage.removeItem('vibe_auto_execute_project');
        sessionStorage.removeItem('vibe_auto_execute_token');
        
        // Trigger execution
        try {
          const triggerResp = await axios.post(
            `${API_BASE_URL}/api/projects/${autoExecuteProjectId}/trigger-handoff-execution`,
            {},
            { headers: { Authorization: `Bearer ${autoExecuteToken}` } }
          );
          
          if (triggerResp.data.status === 'triggered') {
            console.log('✅ Auto-execution triggered successfully');
            
            // Show a message to the user
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: '🚀 **Auto-execution started!**\n\nI\'m analyzing your BRD from D-Suite and creating the application. This may take a few minutes.\n\nYou can watch the progress in real-time below.',
              timestamp: new Date().toISOString(),
            }]);
            
            // Start polling for updates
            setIsContainerLoading(true);
            containerLoadExpectedRef.current = true;
          } else if (triggerResp.data.status === 'already_started') {
            console.log('ℹ️ Execution already started previously at', triggerResp.data.execution_start_time);
            
            // Show a message that execution is already in progress
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: '✅ **Welcome back!**\n\nExecution was already started for this project.',
              timestamp: new Date().toISOString(),
            }]);
            
            // Start polling for updates to show current progress
            setIsContainerLoading(true);
            containerLoadExpectedRef.current = true;
          }
        } catch (err) {
          console.error('Failed to trigger auto-execution:', err);
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: '⚠️ **Auto-execution failed**\n\nThere was an error starting automatic execution. You can manually start by sending a message.',
            timestamp: new Date().toISOString(),
          }]);
        }
      }

      // Load chat history for the current version
      try {
        const chatResp = await axios.get(`${API_BASE_URL}/api/projects/${projectIdToLoad}/chat/v${chatVersion}`);
        if (chatResp.data && chatResp.data.history && chatResp.data.history.length > 0) {
          setMessages(chatResp.data.history);
        }
      } catch (err) {
        console.error("Failed to load chat history:", err);
      }
    };

    if (isAuthenticated) {
      initProject();
    }
  }, [isAuthenticated]);

  // Switch to a project — sets the ID and starts the container in the background
  const switchToProject = async (newProjectId) => {
    if (!newProjectId || newProjectId === currentProjectId) return;
    setCurrentProjectId(newProjectId);
    navigate(`/vibecoding/a/${newProjectId}`);

    // Start the container silently — don't force preview tab, let user stay on chat/code
    try {
      const startResp = await axios.post(
        `${API_BASE_URL}/api/projects/${newProjectId}/start`,
        {},
        {  }
      );
      if (startResp.data.started && startResp.data.preview_url) {
        console.log('🚀 Container starting for switched project:', newProjectId);
        setPreviewUrl(startResp.data.preview_url);
        containerLoadExpectedRef.current = true;
        setIsContainerLoading(true);
        startContainerRetry(startResp.data.preview_url);
        startWorkspacePolling(newProjectId);
      }
    } catch (err) {
      console.warn('Container start on project switch failed (non-critical):', err.message);
    }
  };

  // Switch to a different branch
  const switchToBranch = async (branchName) => {
    try {
      console.log(`🔀 Switching to branch: ${branchName}`);

      // Checkout the branch on backend
      await axios.post(`${API_BASE_URL}/api/git/checkout`, {
        project_id: currentProjectId,
        branch_name: branchName
      });

      setCurrentBranch(branchName);

      // Load commits for this branch
      await loadBranchCommits(currentProjectId, branchName);

      // Load files for this branch
      const filesResp = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/versions/${branchName}/files`);
      const filesMap = filesResp.data.files || {};

      let fullCode = '';
      Object.entries(filesMap).forEach(([filePath, content]) => {
        fullCode += `// FILE: ${filePath}\n${content}\n\n`;
      });

      const fileTree = parseCodeToFiles(fullCode);
      setPreviewCode(fullCode);
      setFullCode(fullCode);
      setFileTree(fileTree);

      // Update preview
      const previewResp = await axios.post(`${API_BASE_URL}/api/projects/${currentProjectId}/versions/workspace/preview`);
      if (previewResp.data.preview_url) {
        containerLoadExpectedRef.current = true;
        setIsContainerLoading(true);
        setPreviewUrl(previewResp.data.preview_url);
        // Only auto-switch if not in code view
        if (activeView !== 'code') {
          setActiveView('preview');
        }
        startContainerRetry(previewResp.data.preview_url);
      }

      // Load chat history for this branch
      try {
        const chatResp = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/chat/${branchName}`);
        if (chatResp.data && chatResp.data.history) {
          setMessages(chatResp.data.history);
        } else {
          setMessages([]);
        }
      } catch (err) {
        console.error('Failed to load chat for branch:', err);
        setMessages([]);
      }

      setShowVersionHistory(false);
    } catch (err) {
      console.error('Failed to switch branch:', err);
    }
  };

  // Load code from a specific commit (checkpoint)
  const loadCommitCheckpoint = async (commitHash) => {
    try {
      setIsCheckpointLoading(true);
      console.log(`🔖 Loading checkpoint: ${commitHash}`);
      console.log(`📍 Current project: ${currentProjectId}`);

      // Find the commit info from branchCommits
      const commitInfo = branchCommits.find(c => c.hash === commitHash);

      // Checkout the commit
      const checkoutResp = await axios.post(`${API_BASE_URL}/api/git/checkpoint`, {
        project_id: currentProjectId,
        version_id: commitHash
      });
      console.log('✅ Checkout response:', checkoutResp.data);

      if (checkoutResp.data.status === 'error') {
        console.error('❌ Checkout failed:', checkoutResp.data.message);
        return;
      }

      // Set viewing checkpoint state
      if (commitInfo) {
        setViewingCheckpoint({
          hash: commitHash,
          message: commitInfo.message,
          date: commitInfo.date
        });
        setShowCheckpointSnackbar(true);

        // Auto-hide snackbar after 5 seconds
        setTimeout(() => {
          setShowCheckpointSnackbar(false);
        }, 5000);
      }

      // Load files from workspace (now at this commit)
      const filesResp = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/versions/workspace/files`);
      const filesMap = filesResp.data.files || {};
      console.log(`📁 Loaded ${Object.keys(filesMap).length} files from workspace`);

      let fullCode = '';
      let htmlContent = '';
      Object.entries(filesMap).forEach(([filePath, content]) => {
        fullCode += `// FILE: ${filePath}\n${content}\n\n`;
        if (filePath.endsWith('.html')) {
          htmlContent = content;
        }
      });

      const fileTree = parseCodeToFiles(fullCode);
      console.log(`🌳 Built file tree with ${fileTree.length} items`);

      setPreviewCode(htmlContent || fullCode);
      setFullCode(fullCode);
      setFileTree(fileTree);

      // Expand all folders
      const allFolderPaths = new Set();
      const collectFolders = (items) => {
        items.forEach(item => {
          if (item.type === 'folder') {
            allFolderPaths.add(item.path);
            if (item.children) {
              collectFolders(item.children);
            }
          }
        });
      };
      collectFolders(fileTree);
      setExpandedFolders(allFolderPaths);
      console.log(`📂 Expanded ${allFolderPaths.size} folders`);

      // Select first file with unique timestamp to force re-render
      const findFirstFile = (items) => {
        for (const item of items) {
          if (item.type === 'file') return item;
          if (item.type === 'folder' && item.children) {
            const found = findFirstFile(item.children);
            if (found) return found;
          }
        }
        return null;
      };
      const firstFile = findFirstFile(fileTree);
      if (firstFile) {
        // Add timestamp to force React to detect change
        setSelectedFile({ ...firstFile, _loadedAt: Date.now() });
        console.log('📄 Selected file:', firstFile.name, `(${firstFile.content?.length || 0} chars)`);
      } else {
        console.warn('⚠️ No file found to select');
      }

      // Get preview URL for the workspace at this commit
      try {
        const previewResp = await axios.post(`${API_BASE_URL}/api/projects/${currentProjectId}/versions/workspace/preview`);
        if (previewResp.data.preview_url) {
          console.log('🌐 Checkpoint preview:', previewResp.data.preview_url);
          console.log('📊 Setting isContainerLoading = true for checkpoint');

          setIsCheckpointLoading(false);
          containerLoadExpectedRef.current = true;
          setIsContainerLoading(true);
          setPreviewUrl(previewResp.data.preview_url);
          setActiveView('preview');

          startContainerRetry(previewResp.data.preview_url);

          console.log('🔄 Container loading started for checkpoint');
        } else {
          setIsCheckpointLoading(false);
        }
      } catch (previewErr) {
        console.error('Failed to get preview URL:', previewErr);
        setIsCheckpointLoading(false);
      }

      console.log('✅ Checkpoint loaded successfully');

    } catch (err) {
      console.error('❌ Failed to load commit checkpoint:', err);
      console.error('Error details:', err.response?.data || err.message);
      setIsCheckpointLoading(false);
    }
  };


  // Reload iframe when previewUrl changes — single effect, no about:blank trick
  // When a container previewUrl arrives, wait 3s for container to fully boot,
  // then start auto-refreshing the iframe every 2s until it loads successfully.
  useEffect(() => {
    // Only handle non-container URL changes (container retries are started imperatively)
    if (previewUrl && !isContainerLoading) {
      setIframeKey(prev => prev + 1);
    }
  }, [previewUrl]);

  // Function to save a new code version
  // Function to start a new chat
  const handleNewChat = async () => {
    const newVersion = chatVersion + 1;
    setChatVersion(newVersion);
    setMessages([]);
    setEditMode(false);
    setSelectedElement(null);
    stopWorkspacePolling();

    // Create a new Git branch for this chat session
    try {
      await axios.post(`${API_BASE_URL}/api/chat/new`, {
        project_id: currentProjectId,
        chat_version: newVersion
      });
      console.log(`🌿 Created new git branch for chat v${newVersion}`);
      // Refresh branches list from backend
      await loadBranchesFromBackend(currentProjectId);
    } catch (err) {
      console.error('Failed to create new git branch:', err);
    }
  };

  // Function to handle new project creation - clears chat and resets state
  const handleCreateProject = (newProjectId) => {
    stopWorkspacePolling();
    // Clear all chat-related state
    setMessages([]);
    setPreviewCode('');
    setFullCode('');
    setPreviewUrl('');
    setFileTree([]);
    setSelectedFile(null);
    setBranches([]);
    setCurrentBranch('main');
    setBranchCommits([]);
    setChatVersion(1);
    setEditMode(false);
    setSelectedElement(null);
    setHoveredElement(null);

    console.log(`🆕 Created new project ${newProjectId}, chat cleared`);
  };

  const toggleFolder = (folderPath) => {
    setExpandedFolders(prev => {
      const newSet = new Set(prev);
      if (newSet.has(folderPath)) {
        newSet.delete(folderPath);
      } else {
        newSet.add(folderPath);
      }
      return newSet;
    });
  };

  const renderFileTreeWithFreeze = (items, level = 0) => {
    return items.map((item, idx) => {
      if (item.type === 'folder') {
        const isExpanded = expandedFolders.has(item.path);
        return (
          <div key={item.path}>
            <div
              onClick={() => toggleFolder(item.path)}
              className="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors text-gray-400 hover:bg-white/5 hover:text-white"
              style={{ paddingLeft: `${12 + level * 16}px` }}
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 flex-shrink-0" />
              ) : (
                <ChevronRight className="w-4 h-4 flex-shrink-0" />
              )}
              <Folder className="w-4 h-4 flex-shrink-0" />
              <span className="truncate">{item.name}</span>
            </div>
            {isExpanded && item.children && (
              <div>{renderFileTreeWithFreeze(item.children, level + 1)}</div>
            )}
          </div>
        );
      } else {
        const isFrozen = frozenFiles.includes(item.path);
        const FreezeIcon = isFrozen ? Lock : Unlock;

        return (
          <div
            key={item.path}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors group ${selectedFile?.path === item.path
              ? 'bg-white/10 text-white'
              : 'text-gray-400 hover:bg-white/5 hover:text-white'
              }`}
            style={{ paddingLeft: `${12 + level * 16}px` }}
          >
            <div className="flex items-center gap-2 flex-1 min-w-0" onClick={() => setSelectedFile(item)}>
              <File className="w-4 h-4 flex-shrink-0" />
              <span className="truncate">{item.name}</span>
            </div>
            {currentProjectId && (
              <button
                onClick={(e) => toggleFileFrozen(item.path, e)}
                disabled={freezeLoading}
                className={`p-1 rounded flex-shrink-0 ${isFrozen
                  ? 'text-yellow-500 hover:text-yellow-600'
                  : 'opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-gray-300'
                  }`}
                title={isFrozen ? 'File is frozen (read-only)' : 'Click to freeze file'}
              >
                <FreezeIcon className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        );
      }
    });
  };

  const renderFileTree = (items, level = 0) => {
    return items.map((item, idx) => {
      if (item.type === 'folder') {
        const isExpanded = expandedFolders.has(item.path);
        return (
          <div key={item.path}>
            <div
              onClick={() => toggleFolder(item.path)}
              className="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors text-gray-400 hover:bg-white/5 hover:text-white"
              style={{ paddingLeft: `${12 + level * 16}px` }}
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 flex-shrink-0" />
              ) : (
                <ChevronRight className="w-4 h-4 flex-shrink-0" />
              )}
              <Folder className="w-4 h-4 flex-shrink-0" />
              <span className="truncate">{item.name}</span>
            </div>
            {isExpanded && item.children && (
              <div>{renderFileTree(item.children, level + 1)}</div>
            )}
          </div>
        );
      } else {
        return (
          <div
            key={item.path}
            onClick={() => setSelectedFile(item)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors ${selectedFile?.path === item.path
              ? 'bg-white/10 text-white'
              : 'text-gray-400 hover:bg-white/5 hover:text-white'
              }`}
            style={{ paddingLeft: `${12 + level * 16}px` }}
          >
            <File className="w-4 h-4 flex-shrink-0" />
            <span className="truncate">{item.name}</span>
          </div>
        );
      }
    });
  };

  const handleSend = async (imageDataUrls = []) => {
    if ((!input.trim() && imageDataUrls.length === 0) || loading) return;

    // Check if a project is selected
    if (!currentProjectId) {
      alert('Please select or create a project first');
      return;
    }

    // Protection against double submissions
    if (loading) return;
    
    // ✅ Set loading immediately for instant feedback
    setLoading(true);
    stopWorkspacePolling(); // stop any previous live polling

    const userMessage = {
      role: 'user',
      content: input,
      images: imageDataUrls.length > 0 ? imageDataUrls : undefined,
      timestamp: new Date().toISOString()
    };

    // Add user message to state immediately for UX
    setMessages(prev => [...prev, userMessage]);
    const currentInput = input;
    setInput('');

    try {
      const payload = {
        prompt: currentInput,
        history: messages,
        project_id: currentProjectId,
        discuss_mode: discussMode,
      };
      if (imageDataUrls.length > 0) {
        payload.images = imageDataUrls;
      }
      const response = await axios.post(`${API_BASE_URL}/api/generate`, payload);

      const aiMessage = {
        role: 'assistant',
        content: response.data.message,
        code: response.data.code,
        versionId: response.data.version_id,
        summary: response.data.summary,
        toolCalls: response.data.tool_calls_log || null,
        suggestions: response.data.suggestions || null,
        metadata: response.data.metadata || null,
        timestamp: new Date().toISOString(),
        id: response.data.message_id
      };

      // Check if we're awaiting task breakdown - if so, don't add the empty message and keep loader active
      const awaitingTaskBreakdown = response.data.metadata?.awaiting_task_breakdown;
      
      if (!awaitingTaskBreakdown && response.data.message) {
        // Only add message if it's not empty and we're not awaiting task breakdown
        setMessages(prev => [...prev, aiMessage]);
      }
      
      setLastMessageId(response.data.message_id);

      if (response.data.code) {
        setVerificationStatus('checking');
      }

      const { project_id, version_id } = response.data;
      if (project_id && project_id !== currentProjectId) {
        // This triggers fetchMessages() in useEffect, which will sync the entire history
        setCurrentProjectId(project_id);
      }

      if (!discussMode) {
        // Always start polling in non-discuss mode to check for tasks
        // Loader will stay active until polling finds tasks or times out
        console.log('🔄 Starting polling - keeping loader active');
        console.log('📊 Current state: loading=', loading, 'isAutonomousPolling=', isAutonomousPolling);
        setIsAutonomousPolling(true);
        // CRITICAL: Keep loading true - polling will set it to false when done
        // Don't call setLoading(false) here!
        
        // ✅ Add safety timeout to prevent infinite loading (90 seconds)
        // setInterval(() => {
        //   setLoading(prev => {
        //     if (prev) {
        //       console.log('⏱️ Safety timeout - forcing loader off after 90 seconds');
        //       setIsAutonomousPolling(false);
        //       // return false;
        //     }
        //     return prev;
        //   });
        // }, 9999);
      } else {
        // In discuss mode, stop loader immediately
        console.log('💬 Discuss mode - stopping loader');
        setLoading(false);
      }

      if (response.data.code) {
        const fullCodeContent = response.data.code;
        const isPatchResponse = /\/\/\s*PATCH:\s*/.test(fullCodeContent);

        if (isPatchResponse) {
          // Patch was applied server-side — reload full workspace files from backend
          try {
            const filesResp = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/versions/workspace/files`);
            const filesMap = filesResp.data.files || {};
            let rebuiltCode = '';
            Object.entries(filesMap).forEach(([filePath, content]) => {
              rebuiltCode += `// FILE: ${filePath}\n${content}\n\n`;
            });
            setFullCode(rebuiltCode);
            setPreviewCode(rebuiltCode);
            const files = parseCodeToFiles(rebuiltCode);
            setFileTree(files);
            const allFolderPaths = new Set();
            const collectFolders = (items) => {
              items.forEach(item => {
                if (item.type === 'folder') { allFolderPaths.add(item.path); if (item.children) collectFolders(item.children); }
              });
            };
            collectFolders(files);
            setExpandedFolders(allFolderPaths);
            const findFirstFile = (items) => {
              for (const item of items) {
                if (item.type === 'file') return item;
                if (item.type === 'folder' && item.children) { const f = findFirstFile(item.children); if (f) return f; }
              }
              return null;
            };
            const firstFile = findFirstFile(files);
            if (firstFile) setSelectedFile(firstFile);

            // After patch, ensure container preview is refreshed
            if (!response.data.preview_url) {
              try {
                const previewResp = await axios.post(`${API_BASE_URL}/api/projects/${currentProjectId}/versions/workspace/preview`);
                if (previewResp.data.preview_url) {
                  console.log('🌐 Restarted container after patch:', previewResp.data.preview_url);
                  containerLoadExpectedRef.current = true;
                  setIsContainerLoading(true);
                  setPreviewUrl(previewResp.data.preview_url);
                  setActiveView('preview');
                  startContainerRetry(previewResp.data.preview_url);
                }
              } catch (previewErr) {
                console.error('Failed to get container preview after patch:', previewErr);
              }
            }
          } catch (err) {
            console.error('Failed to reload workspace after patch:', err);
          }
        } else {
          setFullCode(fullCodeContent); // Store full code
          const tempFiles = parseCodeToFiles(fullCodeContent);
          const firstHtml = tempFiles.find(f => f.name.endsWith('.html'))?.content || fullCodeContent;
          setPreviewCode(firstHtml);
          setIframeKey(prev => prev + 1); // Force iframe refresh

          // Parse code to build file tree
          const code = fullCodeContent;
          const files = parseCodeToFiles(code);
          setFileTree(files);

          // Expand all folders by default
          const allFolderPaths = new Set();
          const collectFolders = (items) => {
            items.forEach(item => {
              if (item.type === 'folder') {
                allFolderPaths.add(item.path);
                if (item.children) {
                  collectFolders(item.children);
                }
              }
            });
          };
          collectFolders(files);
          setExpandedFolders(allFolderPaths);

          // Select first file
          const findFirstFile = (items) => {
            for (const item of items) {
              if (item.type === 'file') return item;
              if (item.type === 'folder' && item.children) {
                const found = findFirstFile(item.children);
                if (found) return found;
              }
            }
            return null;
          };
          const firstFile = findFirstFile(files);
          if (firstFile) {
            setSelectedFile(firstFile);
          }

          // For preview display (not edit mode), extract the first HTML file or use full code
          const findPreviewHtmlFile = (items) => {
            for (const item of items) {
              if (item.type === 'file' && (item.name === 'preview.html' || item.path.endsWith('/preview.html'))) {
                return item.content;
              }
              if (item.type === 'folder' && item.children) {
                const found = findPreviewHtmlFile(item.children);
                if (found) return found;
              }
            }
            for (const item of items) {
              if (item.type === 'file' && item.name.endsWith('.html')) {
                return item.content;
              }
              if (item.type === 'folder' && item.children) {
                const found = findPreviewHtmlFile(item.children);
                if (found) return found;
              }
            }
            return null;
          };

          const htmlContent = findPreviewHtmlFile(files);
          if (htmlContent) {
            setPreviewCode(htmlContent);
          } else if (files.length === 1 && files[0].type === 'file') {
            setPreviewCode(files[0].content);
          }
        } // end non-patch branch
      }

      if (response.data.preview_url) {
        console.log('🌐 Container preview:', response.data.preview_url);
        console.log('📊 Setting isContainerLoading = true');
        containerLoadExpectedRef.current = true;
        setIsContainerLoading(true);
        setPreviewUrl(response.data.preview_url);
        setActiveView('preview');
        // Start health polling — shows iframe once Nginx gateway is up
        startContainerRetry(response.data.preview_url);
        // Start live workspace polling — updates file tree as agent writes files
        startWorkspacePolling(response.data.project_id || currentProjectId);
      } else if (response.data.code) {
        // No container URL, use inline preview
        setPreviewUrl('');
        if (activeView !== 'code') {
          setActiveView('preview');
        }
      }

      // Reload branch commits to show new checkpoint in version history
      if (response.data.version_id) {
        await loadBranchCommits(currentProjectId, currentBranch);
      }
    } catch (error) {
      console.error('Error:', error);
      
      // ✅ Remove temporary status message
      setMessages(prev => prev.filter(msg => !msg.metadata?.temporary));
      
      // ✅ Always reset loading state on error
      setLoading(false);
      setIsAutonomousPolling(false);
      
      // ✅ Handle different error types with appropriate messages
      if (error.response?.status === 401) {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: '🔒 Your session has expired. Please log in again to continue.',
          timestamp: new Date().toISOString(),
          metadata: { type: 'error', auth_required: true }
        }]);
      } else {
        const errorMessage = error.response?.data?.detail || error.message || 'Sorry, there was an error. Please try again.';
        setErrorHeader(errorMessage);
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `❌ I encountered an error: ${errorMessage}`,
          timestamp: new Date().toISOString(),
          metadata: { type: 'error' }
        }]);
      }
    }
    // NOTE: No finally block! We want polling to control the loader state
  };

  /**
   * handleRestore — reverts the project files to the git state that existed
   * BEFORE the user message at `messageIndex` was sent, then puts the prompt
   * back into the chat input so the user can re-send or tweak it.
   *
   * Strategy:
   *   1. Find the assistant message BEFORE the target user message that carries a
   *      versionId/version_id (a git commit hash).  That commit is the state we
   *      want to restore to.
   *   2. If no prior commit exists (first message) we call the backend endpoint
   *      that resets to the very first commit on the branch.
   *   3. Show the amber "Restoring…" loader in both chat and preview.
   *   4. Put the original prompt back in the input box.
   */
  const handleRestore = async (promptText, messageIndex) => {
    if (!currentProjectId) return;

    // Walk backwards through messages to find the most recent assistant message
    // with a versionId that comes BEFORE this user message.
    let targetCommitHash = null;
    const allMsgs = messages; // raw messages array (not processedMessages)
    for (let i = messageIndex - 1; i >= 0; i--) {
      const m = allMsgs[i];
      const vId = m?.versionId || m?.version_id;
      if (m?.role === 'assistant' && vId) {
        targetCommitHash = vId;
        break;
      }
    }

    // Start the amber restoring state
    setIsRestoring(true);
    setLoading(true);
    stopWorkspacePolling();

    // Put the original prompt back in the input so user can re-send
    setInput(promptText);

    try {
      if (targetCommitHash) {
        // Restore to the specific commit that preceded this prompt
        console.log(`🔄 Restoring to commit: ${targetCommitHash}`);
        await loadCommitCheckpoint(targetCommitHash);
      } else {
        // No prior commit — restore to HEAD of first commit (initial state)
        console.log('🔄 Restoring to initial project state (first commit)');
        const commitsResp = await axios.get(
          `${API_BASE_URL}/api/projects/${currentProjectId}/branches/${currentBranch}/commits`
        );
        const commits = commitsResp.data.commits || [];
        if (commits.length > 0) {
          // The oldest commit is the last in the array (most recent first ordering)
          const firstCommit = commits[commits.length - 1];
          await loadCommitCheckpoint(firstCommit.hash);
        }
      }

      // Add a system message to chat confirming the restore
      setMessages(prev => {
        // Slice messages up to (but not including) the target user message and everything after
        const slicedMsgs = prev.slice(0, messageIndex);
        return [
          ...slicedMsgs,
          {
            role: 'assistant',
            content: `↩️ **Restored!** Code has been reverted to the state before this prompt. Your original message has been placed back in the input — feel free to edit and re-send.`,
            timestamp: new Date().toISOString(),
            metadata: { type: 'restore_confirmation' }
          }
        ];
      });

    } catch (err) {
      console.error('Restore failed:', err);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '❌ Restore failed. Please try again or use the Version History panel.',
        timestamp: new Date().toISOString(),
        metadata: { type: 'error' }
      }]);
    } finally {
      setIsRestoring(false);
      setLoading(false);
    }

    if (!currentProjectId || loading || isDeploying) return;

    setIsDeploying(true);
    setDeployStatus(null);

    try {
      // Step 1: Simulate preparation
      await new Promise(resolve => setTimeout(resolve, 1500));

      // Step 2: Call download API to prepare build
      const response = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/download`, {
        responseType: 'blob'
      });

      // Step 3: Trigger download as if "deployed" to a local package
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${currentProjectId}_deploy.zip`);
      document.body.appendChild(link);
      link.click();
      link.remove();

      setDeployStatus('success');
      setTimeout(() => setDeployStatus(null), 5000);
    } catch (error) {
      console.error('Deployment error:', error);
      setDeployStatus('error');
      setTimeout(() => setDeployStatus(null), 5000);
    } finally {
      setIsDeploying(false);
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(previewCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRefresh = () => {
    setIsRefreshing(true);
    setIframeKey(prev => prev + 1);
    setTimeout(() => setIsRefreshing(false), 600);
  };

  const handleDownload = () => {
    const blob = new Blob([previewCode], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'vibecoding-code.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleSendElementToAI = (elementInfo) => {
    const prompt = `Please modify this ${elementInfo.tagName} element. Current details:
- Tag: ${elementInfo.tagName}
- ID: ${elementInfo.id || 'none'}
- Classes: ${elementInfo.className || 'none'}
- Current text: ${elementInfo.textContent || 'none'}
- Current styles: ${JSON.stringify(elementInfo.styles)}

Please suggest improvements or modifications for this element.`;

    setInput(prompt);
    // Focus on chat input
    document.getElementById('chat-input')?.focus();
  };

  const handleUpdateCode = (updatedHTML) => {
    setPreviewCode(updatedHTML);
    setFullCode(updatedHTML);

    // Save as new version
    saveCodeVersion(updatedHTML, previewUrl, fileTree, 'Element edited in preview');
  };

  // ─── VISUAL EDITOR: postMessage-based architecture ───────────────────────────
  // The correct approach (used by Base44, Webflow, Framer) is to inject a script
  // INTO the iframe content (same-origin srcDoc). That script runs inside the
  // iframe and sends postMessage events back to the parent. The parent renders a
  // floating overlay using the received coordinates. We never access
  // contentDocument from the parent.

  // Build the editor injection script that will be injected into the iframe HTML
  const buildEditorScript = () => `
    <script id="__vibe_editor__">
    (function() {
      var hoveredEl = null;
      var selectedEl = null;
      var editMode = false;

      // Listen for edit-mode toggle from parent
      window.addEventListener('message', function(e) {
        if (!e.data || !e.data.type) return;

        if (e.data.type === 'set-edit-mode') {
          editMode = e.data.value;
          if (!editMode) {
            clearHover();
            clearSelection();
          }
        } else if (e.data.type === 'update-element-property') {
          if (selectedEl && e.data.property) {
            if (e.data.property === 'textContent' || e.data.property === 'innerHTML' || e.data.property === 'innerText') {
              selectedEl[e.data.property] = e.data.value;
            } else {
              selectedEl.style[e.data.property] = e.data.value;
            }
          }
        }
      });

      function getElementInfo(el) {
        var rect = el.getBoundingClientRect();
        return {
          tagName: el.tagName,
          id: el.id || '',
          className: (typeof el.className === 'string' ? el.className : '') ,
          textContent: (el.textContent || '').substring(0, 150),
          rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
        };
      }

      function clearHover() {
        window.parent.postMessage({ type: 'element-hover', data: null }, '*');
      }

      function clearSelection() {
        selectedEl = null;
        window.parent.postMessage({ type: 'element-deselect' }, '*');
      }

      document.addEventListener('mouseover', function(e) {
        if (!editMode) return;
        var el = e.target;
        if (!el || el.tagName === 'HTML' || el.tagName === 'BODY') {
          clearHover();
          return;
        }
        hoveredEl = el;
        window.parent.postMessage({ type: 'element-hover', data: getElementInfo(el) }, '*');
      }, true);

      document.addEventListener('mouseout', function(e) {
        if (!editMode) return;
        hoveredEl = null;
        clearHover();
      }, true);

      document.addEventListener('click', function(e) {
        if (!editMode) return;
        e.preventDefault();
        e.stopPropagation();
        var el = e.target;
        if (!el || el.tagName === 'HTML' || el.tagName === 'BODY') return;
        selectedEl = el;
        var info = getElementInfo(el);
        info.mouseX = e.clientX;
        info.mouseY = e.clientY;
        window.parent.postMessage({ type: 'element-selected', data: info }, '*');
      }, true);

      // Scroll events: re-broadcast hover rect when page scrolls
      document.addEventListener('scroll', function() {
        if (!editMode || !hoveredEl) return;
        window.parent.postMessage({ type: 'element-hover', data: getElementInfo(hoveredEl) }, '*');
      }, true);
    })();
    <\/script>
  `;

  // Inject editor script into preview HTML (srcDoc only – not cross-origin URLs)
  const injectEditorScript = (html) => {
    if (!html) return html;
    const script = buildEditorScript();
    // Inject before </body> if exists, otherwise append
    if (html.includes('</body>')) {
      return html.replace('</body>', script + '</body>');
    }
    return html + script;
  };

  // Listen for postMessage events from iframe
  useEffect(() => {
    const handleMessage = (event) => {
      try {
        const msg = event.data;
        if (!msg || !msg.type) return;

        console.log('📥 Received message from iframe:', msg.type, msg);

        if (msg.type === 'element-hover') {
          if (!msg.data) {
            setHoveredElement(null);
            return;
          }
          // Coordinates from iframe are relative to iframe viewport.
          // We need to offset by the iframe element's position in parent.
          const iframe = iframeRef.current;
          const container = iframeContainerRef.current;
          if (!iframe || !container) return;
          const iframeRect = iframe.getBoundingClientRect();
          const containerRect = container.getBoundingClientRect();
          const offsetTop = iframeRect.top - containerRect.top;
          const offsetLeft = iframeRect.left - containerRect.left;
          setHoveredElement({
            ...msg.data,
            rect: {
              top: msg.data.rect.top + offsetTop,
              left: msg.data.rect.left + offsetLeft,
              width: msg.data.rect.width,
              height: msg.data.rect.height,
            }
          });
        } else if (msg.type === 'element-selected') {
          const iframe = iframeRef.current;
          const container = iframeContainerRef.current;
          if (!iframe || !container) return;
          const iframeRect = iframe.getBoundingClientRect();
          const containerRect = container.getBoundingClientRect();
          const offsetTop = iframeRect.top - containerRect.top;
          const offsetLeft = iframeRect.left - containerRect.left;

          const elementData = {
            ...msg.data,
            rect: {
              top: msg.data.rect.top + offsetTop,
              left: msg.data.rect.left + offsetLeft,
              width: msg.data.rect.width,
              height: msg.data.rect.height,
            }
          };

          setSelectedElement(elementData);

          // Position menu at mouse click position (offset from iframe top-left)
          const menuX = iframeRect.left + (msg.data.mouseX || (msg.data.rect.left + msg.data.rect.width / 2));
          const menuY = iframeRect.top + (msg.data.mouseY || msg.data.rect.top);
          // Clamp so menu doesn't go off-screen right/bottom
          const clampedX = Math.min(menuX, window.innerWidth - 220);
          const clampedY = Math.min(menuY, window.innerHeight - 320);

          setEditMenu({
            visible: true,
            element: elementData,
            position: { x: clampedX, y: clampedY }
          });
        } else if (msg.type === 'element-deselect') {
          setSelectedElement(null);
          setEditMenu({ ...editMenu, visible: false });
        }
      } catch (err) {
        // Silently ignore postMessage errors from other sources
        console.debug('Ignored postMessage error:', err.message);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  // Tell iframe to enable/disable edit mode via postMessage (NO iframe reload!)
  // The preview must stay visually identical — like Base44/Webflow.
  useEffect(() => {
    if (!editMode) {
      setSelectedElement(null);
      setHoveredElement(null);
    }
    // Send edit-mode state to iframe's injected script
    const iframe = iframeRef.current;
    if (iframe && iframe.contentWindow) {
      console.log('📤 Sending edit mode message to iframe:', editMode);
      iframe.contentWindow.postMessage({ type: 'set-edit-mode', value: editMode }, '*');
    } else {
      console.warn('⚠️ Iframe or contentWindow not available');
    }
  }, [editMode]);

  // Close version history dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (showVersionHistory && !event.target.closest('.version-history-container')) {
        setShowVersionHistory(false);
      }
      if (showUserMenu && !event.target.closest('.user-menu-container')) {
        setShowUserMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showVersionHistory, showUserMenu]);

  // Cleanup poll timer on unmount
  useEffect(() => {
    return () => {
      if (containerPollIntervalRef.current) {
        clearTimeout(containerPollIntervalRef.current);
      }
    };
  }, []);

  // ─── END VISUAL EDITOR ───────────────────────────────────────────────────────

  const handleElementEdit = async () => {
    if (!editPrompt.trim() || !selectedElement) return;

    const editMessage = {
      role: 'user',
      content: `Edit the ${selectedElement.tagName?.toLowerCase()} element: ${editPrompt}\n\nCurrent element: <${selectedElement.tagName?.toLowerCase()}${selectedElement.id ? ` id="${selectedElement.id}"` : ''}${selectedElement.className ? ` class="${selectedElement.className}"` : ''}>${selectedElement.textContent?.substring(0, 50)}</${selectedElement.tagName?.toLowerCase()}>\n\nOnly modify this specific element, keep everything else the same.`,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, editMessage]);
    setEditPrompt('');
    setLoading(true);

    // Persist user message to DB
    try {
      const token = localStorage.getItem('vibecoding_token');
      if (currentProjectId) {
        await axios.post(`${API_BASE_URL}/api/projects/${currentProjectId}/messages`, {
          id: `msg_e_${Date.now()}`,
          role: 'user',
          content: editMessage.content,
          timestamp: editMessage.timestamp
        });
      }
    } catch (error) {
      console.error('Failed to persist edit message:', error);
    }

    try {
      const response = await axios.post(`${API_BASE_URL}/api/generate`, {
        prompt: editMessage.content,
        history: messages,
        project_id: currentProjectId
      });

      const aiMessage = {
        role: 'assistant',
        content: response.data.message,
        code: response.data.code,
        versionId: response.data.version_id,
        toolCalls: response.data.tool_calls_log || null,
        suggestions: response.data.suggestions || null,
        timestamp: new Date().toISOString()
      };

      setMessages(prev => [...prev, aiMessage]);

      if (response.data.code) {
        const fullCodeContent = response.data.code;
        setFullCode(fullCodeContent);
        setPreviewCode(fullCodeContent);

        const code = fullCodeContent;
        const files = parseCodeToFiles(code);
        setFileTree(files);

        // Expand all folders
        const allFolderPaths = new Set();
        const collectFolders = (items) => {
          items.forEach(item => {
            if (item.type === 'folder') {
              allFolderPaths.add(item.path);
              if (item.children) {
                collectFolders(item.children);
              }
            }
          });
        };
        collectFolders(files);
        setExpandedFolders(allFolderPaths);

        // Select first file
        const findFirstFile = (items) => {
          for (const item of items) {
            if (item.type === 'file') return item;
            if (item.type === 'folder' && item.children) {
              const found = findFirstFile(item.children);
              if (found) return found;
            }
          }
          return null;
        };
        const firstFile = findFirstFile(files);
        if (firstFile) {
          setSelectedFile(firstFile);
        }

        // Find HTML for preview
        const findPreviewHtmlFile = (items) => {
          for (const item of items) {
            if (item.type === 'file' && (item.name === 'preview.html' || item.path.endsWith('/preview.html'))) {
              return item.content;
            }
            if (item.type === 'folder' && item.children) {
              const found = findPreviewHtmlFile(item.children);
              if (found) return found;
            }
          }

          for (const item of items) {
            if (item.type === 'file' && item.name.endsWith('.html')) {
              return item.content;
            }
            if (item.type === 'folder' && item.children) {
              const found = findPreviewHtmlFile(item.children);
              if (found) return found;
            }
          }
          return null;
        };

        const htmlContent = findPreviewHtmlFile(files);
        if (htmlContent) {
          setPreviewCode(htmlContent);
        } else if (files.length === 1 && files[0].type === 'file') {
          setPreviewCode(files[0].content);
        }
      }

      // Update preview URL if provided
      if (response.data.preview_url) {
        console.log('🌐 Container preview:', response.data.preview_url);
        containerLoadExpectedRef.current = true;
        setIsContainerLoading(true);
        setPreviewUrl(response.data.preview_url);
        setActiveView('preview');
        // Start retry loop imperatively — bypasses React batching issues
        startContainerRetry(response.data.preview_url);
      }

      // Reload branches to show new commit
      await loadBranchesFromBackend(currentProjectId);

      setSelectedElement(null);
    } catch (error) {
      console.error('Error:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, there was an error editing the element. Please try again.',
        timestamp: new Date().toISOString()
      }]);
    } finally {
      setLoading(false);
    }
  };

  // Format timestamp for display
  const formatTimestamp = (timestamp) => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;

    // Show time for today, date for older
    const isToday = date.toDateString() === now.toDateString();
    if (isToday) {
      return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    }

    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  };

  // Parse code to extract files and build tree structure
  const parseCodeToFiles = (code) => {
    // Check if code contains file markers
    const fileMarkerRegex = /\/\/\s*FILE:\s*([^\n]+)|#\s*FILE:\s*([^\n]+)|<!--\s*FILE:\s*([^\n]+)\s*-->/gi;
    const matches = [...code.matchAll(fileMarkerRegex)];

    if (matches.length > 0) {
      // Collect all file blocks, deduplicating by cleaned path (last occurrence wins)
      const fileMap = new Map();

      for (let i = 0; i < matches.length; i++) {
        const match = matches[i];
        const rawFilename = (match[1] || match[2] || match[3]).trim();
        // Strip "(Updated)" suffix that some AI models append
        const filename = rawFilename.replace(/\s*\(Updated\)\s*$/i, '').trim();
        if (!filename || filename === 'metadata.json') continue;

        const startPos = match.index + match[0].length;
        const endPos = i < matches.length - 1 ? matches[i + 1].index : code.length;
        let content = code.substring(startPos, endPos).trim();

        // Skip entries whose content is only SEARCH/REPLACE artifacts
        if (/^<<<\s*SEARCH/.test(content) && !content.includes('<!DOCTYPE') && !content.includes('<html')) {
          continue;
        }

        // Only keep entries with actual content (skip empty "// FILE:" labels)
        if (content) {
          fileMap.set(filename, {
            name: filename.split('/').pop(),
            path: filename,
            content: content,
            type: 'file'
          });
        }
      }

      const files = [...fileMap.values()];
      if (files.length > 0) {
        return buildFileTree(files);
      }
    }

    // Fallback: single file - detect type by content
    {
      let filename = 'app.py';
      if (code.includes('from flask') || code.includes('Flask(')) {
        filename = 'app.py';
      } else if (code.includes('from django')) {
        filename = 'manage.py';
      } else if (code.includes('from fastapi')) {
        filename = 'main.py';
      } else if (code.includes('<!DOCTYPE') || code.includes('<html')) {
        filename = 'index.html';
      } else if (code.includes('import React') || code.includes('from react')) {
        filename = 'App.jsx';
      } else if (code.includes('const express') || code.includes('require(')) {
        filename = 'server.js';
      }

      return [{
        name: filename,
        path: filename,
        content: code,
        type: 'file',
        isExpanded: false
      }];
    }
  };

  // Build hierarchical tree from flat file list
  const buildFileTree = (files) => {
    const tree = [];
    const folderMap = new Map();

    // Sort files by path to ensure folders come before their contents
    files.sort((a, b) => a.path.localeCompare(b.path));

    files.forEach(file => {
      const parts = file.path.split('/');

      if (parts.length === 1) {
        // Root level file
        tree.push({
          ...file,
          isExpanded: false
        });
      } else {
        // Nested file - create folder structure
        let currentPath = '';
        let currentLevel = tree;

        for (let i = 0; i < parts.length - 1; i++) {
          const folderName = parts[i];
          currentPath = currentPath ? `${currentPath}/${folderName}` : folderName;

          let folder = folderMap.get(currentPath);

          if (!folder) {
            folder = {
              name: folderName,
              path: currentPath,
              type: 'folder',
              children: [],
              isExpanded: true
            };
            folderMap.set(currentPath, folder);
            currentLevel.push(folder);
          }

          currentLevel = folder.children;
        }

        // Add file to its parent folder
        currentLevel.push({
          ...file,
          isExpanded: false
        });
      }
    });

    return tree;
  };

  // Get the best available HTML content for inline preview / edit mode.
  // Priority: previewCode (already extracted HTML) > HTML from fileTree > fullCode fallback
  const getPreviewHtml = () => {
    // If previewCode is set and looks like HTML, use it
    if (previewCode && (previewCode.includes('<html') || previewCode.includes('<!DOCTYPE') || previewCode.includes('<body') || previewCode.includes('<div'))) {
      return previewCode;
    }
    // Search fileTree for an HTML file
    const findHtml = (items) => {
      if (!items) return null;
      // Priority 1: preview.html
      for (const item of items) {
        if (item.type === 'file' && (item.name === 'preview.html' || item.name === 'index.html')) return item.content;
        if (item.type === 'folder' && item.children) {
          const found = findHtml(item.children);
          if (found) return found;
        }
      }
      // Priority 2: any .html
      for (const item of items) {
        if (item.type === 'file' && item.name.endsWith('.html')) return item.content;
        if (item.type === 'folder' && item.children) {
          const found = findHtml(item.children);
          if (found) return found;
        }
      }
      return null;
    };
    const htmlFromTree = findHtml(fileTree);
    if (htmlFromTree) return htmlFromTree;
    // If fullCode looks like HTML, use it; otherwise show a waiting message
    if (fullCode && (fullCode.includes('<html') || fullCode.includes('<!DOCTYPE'))) {
      return fullCode;
    }
    return `<!DOCTYPE html><html><head><style>
      body { margin:0; height:100vh; display:flex; align-items:center; justify-content:center;
             background:#0A0A0F; color:#9ca3af; font-family:system-ui,sans-serif; text-align:center; }
      .icon { font-size:3rem; margin-bottom:1rem; }
      h2 { color:#e5e7eb; font-size:1.1rem; margin:0 0 0.5rem; }
      p { font-size:0.85rem; margin:0; }
    </style></head><body><div><div class="icon">⏳</div><h2>Starting your application...</h2><p>Your app is being prepared. The preview will appear shortly.</p></div></body></html>`;
  };

  // pollUntilReady is handled directly via startContainerRetry above

  // Called from iframe onLoad — if container is loading and iframe got real content, stop retrying
  const handleIframeLoad = () => {
    // Only act if we're actively waiting for a container
    if (containerLoadExpectedRef.current) {
      const iframe = iframeRef.current;

      // Ignore about:blank loads (fired when iframeKey changes before real URL loads)
      try {
        const src = iframe?.contentWindow?.location?.href || '';
        if (src === 'about:blank' || src === '') {
          return; // not real content yet
        }
      } catch {
        // Cross-origin means real content is being served — fall through to success check
      }

      // Check if the iframe got real content or a browser error page
      let isErrorPage = false;
      try {
        const doc = iframe?.contentDocument || iframe?.contentWindow?.document;
        const bodyText = doc?.body?.innerText || '';
        if (
          bodyText.includes("didn't send any data") ||
          bodyText.includes('ERR_EMPTY_RESPONSE') ||
          bodyText.includes('ERR_CONNECTION_REFUSED') ||
          bodyText.includes('This site can') ||
          bodyText.includes('refused to connect')
        ) {
          isErrorPage = true;
        }
      } catch {
        // Cross-origin block = real content served by container, not an error page
        isErrorPage = false;
      }

      if (!isErrorPage) {
        // Real content loaded — stop retrying, clear loader
        console.log('✅ Container content loaded — stopping retry loop');
        if (containerPollIntervalRef.current) {
          clearTimeout(containerPollIntervalRef.current);
          containerPollIntervalRef.current = null;
        }
        containerLoadExpectedRef.current = false;
        setIsContainerLoading(false);
      }
      // If it IS an error page, the retry loop keeps firing
    }

    const iframe = iframeRef.current;
    if (iframe && iframe.contentWindow) {
      try {
        iframe.contentWindow.postMessage({ type: 'set-edit-mode', value: editMode }, '*');
      } catch { /* cross-origin, ignore */ }
    }
  };

  return (
    <div className={`h-screen flex flex-col transition-colors ${darkMode ? 'bg-[#0A0A0F] text-white' : 'bg-gray-100 text-gray-900'}`}>
      <Header
        chatVersion={`v${chatVersion}`}
        user={user}
        darkMode={darkMode}
        setDarkMode={setDarkMode}
        showUserMenu={showUserMenu}
        setShowUserMenu={setShowUserMenu}
        projects={projects}
        currentProjectId={currentProjectId}
        setCurrentProjectId={switchToProject}
        showProjectDropdown={showProjectDropdown}
        setShowProjectDropdown={setShowProjectDropdown}
        onNewChat={handleNewChat}
        onCreateProject={handleCreateProject}
        onGitClick={() => setShowGitPanel(true)}
        isDeploying={isDeploying}
        deployStatus={deployStatus}
        previewCode={previewCode}
        loading={loading}
        onLogout={logout}
        branches={branches}
        currentBranch={currentBranch}
        onBranchSwitch={switchToBranch}
        formatTimestamp={formatTimestamp}
      />

      {/* Error/Status Banner */}
      {(errorHeader || deployStatus === 'success') && (
        <div className={`h-10 flex items-center justify-center px-6 text-sm animate-in slide-in-from-top duration-300 ${deployStatus === 'success' ? 'bg-green-600/20 text-green-300' : 'bg-red-600/20 text-red-300'
          }`}>
          <div className="flex items-center gap-2">
            {deployStatus === 'success' ? (
              <Check className="w-4 h-4" />
            ) : (
              <Zap className="w-4 h-4" />
            )}
            <span>{deployStatus === 'success' ? 'Project successfully deployed and downloaded!' : errorHeader}</span>
          </div>
          <button
            onClick={() => { setErrorHeader(null); setDeployStatus(null); }}
            className="ml-4 hover:text-white"
          >
            <Plus className="w-4 h-4 rotate-45" />
          </button>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Right Panel - Preview/Code */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          {/* View Tabs */}
          <div className={`h-12 border-b flex items-center justify-between px-4 sticky top-0 z-10 ${darkMode ? 'border-white/10 bg-[#0F0F14]' : 'border-gray-200 bg-gray-50'
            }`}>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setActiveView('preview')}
                className={`${activeView === 'preview'
                  ? darkMode ? 'bg-white/10 text-white' : 'bg-gray-200 text-gray-900'
                  : darkMode ? 'text-white hover:bg-white/5' : 'text-gray-600 hover:bg-gray-100'
                  }`}
              >
                <Eye className="w-4 h-4 inline mr-2" />
                Preview
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setActiveView('code')}
                className={`${activeView === 'code'
                  ? darkMode ? 'bg-white/10 text-white' : 'bg-gray-200 text-gray-900'
                  : darkMode ? 'text-white hover:bg-white/5' : 'text-gray-600 hover:bg-gray-100'
                  }`}
              >
                <Code className="w-4 h-4 inline mr-2" />
                Code
              </Button>
            </div>


            {previewCode && activeView === 'preview' && (
              <div className="flex items-center gap-2">
                {/* Screen Size Selector */}
                <div className={`flex items-center gap-1 px-2 py-1 rounded-lg transition-colors ${darkMode ? 'bg-white/5' : 'bg-gray-200'
                  }`}>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setScreenSize('mobile')}
                    className={`h-8 w-8 transition-colors ${screenSize === 'mobile'
                      ? darkMode ? 'bg-white/20 text-white' : 'bg-gray-300 text-gray-900'
                      : darkMode ? 'text-white hover:bg-white/10' : 'text-gray-600 hover:bg-gray-300'
                      }`}
                    title="Mobile (375px)"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <rect x="7" y="2" width="10" height="20" rx="2" strokeWidth="2" />
                    </svg>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setScreenSize('tablet')}
                    className={`h-8 w-8 transition-colors ${screenSize === 'tablet'
                      ? darkMode ? 'bg-white/20 text-white' : 'bg-gray-300 text-gray-900'
                      : darkMode ? 'text-white hover:bg-white/10' : 'text-gray-600 hover:bg-gray-300'
                      }`}
                    title="Tablet (768px)"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <rect x="4" y="3" width="16" height="18" rx="2" strokeWidth="2" />
                    </svg>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setScreenSize('desktop')}
                    className={`h-8 w-8 transition-colors ${screenSize === 'desktop'
                      ? darkMode ? 'bg-white/20 text-white' : 'bg-gray-300 text-gray-900'
                      : darkMode ? 'text-white hover:bg-white/10' : 'text-gray-600 hover:bg-gray-300'
                      }`}
                    title="Desktop (100%)"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <rect x="2" y="4" width="20" height="12" rx="2" strokeWidth="2" />
                      <path d="M8 20h8" strokeWidth="2" />
                      <path d="M12 16v4" strokeWidth="2" />
                    </svg>
                  </Button>
                </div>

                {/* Edit Mode Toggle */}
                <Button
                  variant={editMode ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setEditMode(!editMode)}
                  className={`transition-colors ${editMode
                    ? 'bg-purple-600 text-white hover:bg-purple-700'
                    : darkMode
                      ? 'bg-white/5 hover:bg-white/10 text-white'
                      : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
                    }`}
                  title="Edit Mode - Click elements to edit"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                  {editMode ? 'Editing' : 'Edit'}
                </Button>

                <div className={`h-6 w-px transition-colors ${darkMode ? 'bg-white/10' : 'bg-gray-200'}`} />

                <Button
                  size="icon"
                  onClick={handleRefresh}
                  className={`!border-0 ${darkMode ? '!bg-white/5 hover:!bg-white/10 !text-white' : '!bg-gray-200 hover:!bg-gray-300 !text-gray-700'
                    }`}
                  title="Refresh Preview"
                >
                  <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                </Button>

                {previewUrl && (
                  <Button
                    size="icon"
                    onClick={() => window.open(previewUrl, '_blank')}
                    className={`!border-0 ${darkMode ? '!bg-white/5 hover:!bg-white/10 !text-white' : '!bg-gray-200 hover:!bg-gray-300 !text-gray-700'
                      }`}
                    title="Open in new tab"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </Button>
                )}
                {/* <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCopy}
                  className="bg-white/5 hover:bg-white/10 text-white"
                >
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  {copied ? 'Copied' : 'Copy'}
                </Button> */}
                {/* <Button 
                  variant="ghost"
                  size="sm"
                  onClick={handleDownload}
                  className="bg-white/5 hover:bg-white/10 text-white"
                >
                  <Download className="w-4 h-4" />
                  Download
                </Button> */}
              </div>
            )}

            {previewCode && activeView === 'code' && (
              <div className="flex items-center gap-2">
                {/* <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCopy}
                  className="bg-white/5 hover:bg-white/10 text-white"
                >
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  {copied ? 'Copied' : 'Copy'}
                </Button> */}
                {/* <Button 
                  variant="ghost"
                  size="sm"
                  onClick={handleDownload}
                  className="bg-white/5 hover:bg-white/10 text-white"
                >
                  <Download className="w-4 h-4" />
                  Download
                </Button> */}
              </div>
            )}
          </div>

          {/* Content Area */}
          <div className={`flex-1 relative overflow-hidden min-h-0 flex flex-col transition-colors ${darkMode ? 'bg-[#0A0A0F]' : 'bg-white'
            }`}>
            {!previewCode && !previewUrl ? (
              <div className="h-full flex items-center justify-center">
                <div className="text-center">
                  <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 flex items-center justify-center mx-auto mb-4">
                    <Sparkles className="w-10 h-10 text-purple-400" />
                  </div>
                  <h3 className={`text-xl font-semibold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>No Preview Yet</h3>
                  <p className={darkMode ? 'text-gray-400' : 'text-gray-500'}>Start chatting to generate your app</p>
                </div>
              </div>
            ) : activeView === 'preview' ? (
              <div className="h-full flex flex-col">

                {/* Edit Mode Banner */}
                {editMode && (
                  <div className="flex-shrink-0 bg-purple-600/20 border-b border-purple-500/30 px-4 py-2">
                    <div className="flex items-center justify-between">
                      <div className={`flex items-center gap-2 text-sm ${darkMode ? 'text-purple-200' : 'text-purple-700'}`}>
                        <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                        </svg>
                        <span>Edit Mode — hover over any element to highlight it, click to select and edit</span>
                      </div>
                      {selectedElement && (
                        <button
                          onClick={() => { setSelectedElement(null); setHoveredElement(null); }}
                          className="text-purple-300 hover:text-white text-xs px-2 py-0.5 rounded border border-purple-500/40 hover:border-purple-400"
                        >
                          Clear selection
                        </button>
                      )}
                    </div>
                  </div>
                )}

                <div
                  className={`flex-1 relative flex items-center justify-center transition-colors ${darkMode ? 'bg-[#0A0A0F]' : 'bg-gray-200'
                    }`}
                >
                  <div
                    className={`h-full transition-all duration-300 relative ${screenSize === 'mobile' ? 'w-[375px]' :
                      screenSize === 'tablet' ? 'w-[768px]' :
                        'w-full'
                      }`}
                    style={{
                      boxShadow: screenSize !== 'desktop' ? (editMode ? '0 0 0 1px rgba(0,0,0,0.1)' : '0 0 0 1px rgba(255,255,255,0.1)') : 'none'
                    }}
                  >
                    <iframe
                      ref={iframeRef}
                      key={iframeKey}
                      src={previewUrl || undefined}
                      srcDoc={!previewUrl ? injectEditorScript(getPreviewHtml()) : undefined}
                      className="w-full h-full border-0"
                      title="Preview"
                      sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                      onLoad={() => {
                        handleIframeLoad();
                      }}
                    />

                    {/* Container / Checkpoint / Restoring loader overlay */}
                    {(isRestoring || isCheckpointLoading || (isContainerLoading && previewUrl && (verificationStatus !== 'completed' && verificationStatus !== 'failed'))) && (
                      <div className={`absolute inset-0 z-20 flex flex-col items-center justify-center backdrop-blur-sm ${darkMode ? 'bg-[#0A0A0F]/60' : 'bg-white/60'
                        }`}>
                        {/* Animated rings */}
                        <div className="relative flex items-center justify-center mb-8">
                          <div className={`absolute w-24 h-24 rounded-full border-2 animate-ping ${isRestoring ? 'border-amber-500/20' : 'border-purple-500/20'}`} style={{ animationDuration: '2s' }} />
                          <div className={`absolute w-20 h-20 rounded-full border animate-ping ${isRestoring ? 'border-amber-400/30' : 'border-purple-400/30'}`} style={{ animationDuration: '1.5s', animationDelay: '0.3s' }} />
                          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center shadow-lg animate-pulse ${isRestoring ? 'bg-gradient-to-br from-amber-500 to-orange-500 shadow-amber-500/30' : 'bg-gradient-to-br from-purple-600 to-pink-600 shadow-purple-500/30'}`}>
                            <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              {isRestoring ? (
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                              ) : isCheckpointLoading ? (
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                              ) : (
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 12h14M12 5l7 7-7 7" />
                              )}
                            </svg>
                          </div>
                        </div>

                        {/* Spinning arc */}
                        <div className="relative w-12 h-12 mb-6">
                          <svg className="w-12 h-12 animate-spin" viewBox="0 0 48 48" fill="none">
                            <circle cx="24" cy="24" r="20" stroke={isRestoring ? 'rgba(245,158,11,0.15)' : 'rgba(168,85,247,0.15)'} strokeWidth="3" />
                            <path d="M24 4 A20 20 0 0 1 44 24" stroke={`url(#${isRestoring ? 'gradLoaderAmber' : 'gradLoader'})`} strokeWidth="3" strokeLinecap="round" />
                            <defs>
                              <linearGradient id="gradLoader" x1="0%" y1="0%" x2="100%" y2="0%">
                                <stop offset="0%" stopColor="#a855f7" />
                                <stop offset="100%" stopColor="#ec4899" />
                              </linearGradient>
                              <linearGradient id="gradLoaderAmber" x1="0%" y1="0%" x2="100%" y2="0%">
                                <stop offset="0%" stopColor="#f59e0b" />
                                <stop offset="100%" stopColor="#f97316" />
                              </linearGradient>
                            </defs>
                          </svg>
                        </div>

                        {/* Text */}
                        <h3 className={`text-lg font-semibold mb-1 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
                          {isRestoring ? 'Restoring...' : verificationStatus === 'checking' ? 'Verifying deployment' : isCheckpointLoading ? 'Restoring session snapshot' : 'Activating live instance'}
                        </h3>
                        <p className={`text-xs ${darkMode ? 'text-[#858585]' : 'text-gray-400'}`}>
                          {isRestoring ? 'Reverting files to previous state...' : verificationStatus === 'checking' ? 'Checking for errors & matching expectations...' : isCheckpointLoading ? 'Rebuilding environment...' : 'Preparing business preview...'}
                        </p>

                        {/* Animated dots progress */}
                        <div className="flex items-center gap-1.5 mt-5">
                          {[0, 1, 2, 3, 4].map(i => (
                            <div
                              key={i}
                              className={`w-1.5 h-1.5 rounded-full ${isRestoring ? 'bg-amber-500' : 'bg-purple-500'}`}
                              style={{
                                animation: 'containerDotBounce 1.2s ease-in-out infinite',
                                animationDelay: `${i * 0.15}s`
                              }}
                            />
                          ))}
                        </div>

                        <style>{`
                          @keyframes containerDotBounce {
                            0%, 80%, 100% { transform: scaleY(1); opacity: 0.4; }
                            40% { transform: scaleY(1.8); opacity: 1; }
                          }
                        `}</style>
                      </div>
                    )}

                    {/* Overlay container – pointer-events none preserves iframe scrolling */}
                    <div
                      ref={iframeContainerRef}
                      className="absolute inset-0 pointer-events-none"
                      style={{ zIndex: 10 }}
                    >
                      {/* Hover highlight */}
                      {editMode && hoveredElement && !selectedElement && (
                        <div
                          className="absolute pointer-events-none transition-all duration-75"
                          style={{
                            top: hoveredElement.rect.top,
                            left: hoveredElement.rect.left,
                            width: hoveredElement.rect.width,
                            height: hoveredElement.rect.height,
                            outline: '2px solid #a855f7',
                            outlineOffset: '1px',
                            boxShadow: '0 0 0 4px rgba(168, 85, 247, 0.15)',
                          }}
                        >
                          <div
                            className="absolute px-2 py-0.5 bg-purple-600 text-white text-xs rounded font-mono whitespace-nowrap"
                            style={{ top: '-22px', left: 0 }}
                          >
                            {hoveredElement.tagName?.toLowerCase()}
                            {hoveredElement.id && <span className="text-purple-200">#{hoveredElement.id}</span>}
                            {hoveredElement.className && <span className="text-purple-200">.{hoveredElement.className.trim().split(/\s+/)[0]}</span>}
                          </div>
                        </div>
                      )}

                      {/* Selection highlight */}
                      {editMode && selectedElement && (
                        <div
                          className="absolute pointer-events-none"
                          style={{
                            top: selectedElement.rect.top,
                            left: selectedElement.rect.left,
                            width: selectedElement.rect.width,
                            height: selectedElement.rect.height,
                            outline: '2px solid #8b5cf6',
                            outlineOffset: '1px',
                            background: 'rgba(139, 92, 246, 0.08)',
                            boxShadow: '0 0 0 4px rgba(139, 92, 246, 0.25)',
                          }}
                        >
                          <div
                            className="absolute px-2 py-0.5 bg-violet-600 text-white text-xs rounded font-mono whitespace-nowrap flex items-center gap-1"
                            style={{ top: '-22px', left: 0 }}
                          >
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                            {selectedElement.tagName?.toLowerCase()}
                            {selectedElement.id && <span className="text-violet-200">#{selectedElement.id}</span>}
                            {selectedElement.className && <span className="text-violet-200">.{selectedElement.className.trim().split(/\s+/)[0]}</span>}
                          </div>
                          {['tl', 'tr', 'bl', 'br'].map(c => (
                            <div key={c} className={`absolute w-2.5 h-2.5 bg-violet-500 rounded-sm border border-white ${c === 'tl' ? '-top-1.5 -left-1.5' : c === 'tr' ? '-top-1.5 -right-1.5' : c === 'bl' ? '-bottom-1.5 -left-1.5' : '-bottom-1.5 -right-1.5'
                              }`} />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Screen size label */}
                  {screenSize !== 'desktop' && (
                    <div className="absolute bottom-4 right-4 px-3 py-1.5 rounded-lg bg-black/50 backdrop-blur-sm text-xs text-white">
                      {screenSize === 'mobile' ? '375px' : '768px'}
                    </div>
                  )}
                </div>

                {/* Edit Prompt Panel */}
                {editMode && selectedElement && (
                  <div className={`absolute bottom-0 left-0 right-0 z-30 border-t backdrop-blur-sm p-4 shadow-2xl transition-colors ${darkMode
                    ? 'border-white/10 bg-[#0F0F14]/95 text-white'
                    : 'border-gray-200 bg-white/95 text-gray-900'
                    }`}>
                    <div className="max-w-4xl mx-auto">
                      <div className="mb-2 flex items-center justify-between">
                        <div className={`flex items-center gap-2 text-sm ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                          <span className={`px-2 py-0.5 rounded font-mono text-xs ${darkMode ? 'bg-purple-600/20 text-purple-300' : 'bg-purple-100 text-purple-700'
                            }`}>
                            {selectedElement.tagName?.toLowerCase()}
                            {selectedElement.id && `#${selectedElement.id}`}
                            {selectedElement.className && `.${selectedElement.className.split(' ')[0]}`}
                          </span>
                          <span>Selected</span>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => {
                            setSelectedElement(null);
                            setEditPrompt('');
                          }}
                          className={`h-8 w-8 transition-colors ${darkMode ? 'text-gray-400 hover:text-white' : 'text-gray-500 hover:text-gray-900'}`}
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </Button>
                      </div>
                      <div className="relative">
                        <input
                          type="text"
                          value={editPrompt}
                          onChange={(e) => setEditPrompt(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && editPrompt.trim()) {
                              handleElementEdit();
                            }
                          }}
                          placeholder={`Edit this ${selectedElement.tagName?.toLowerCase()}... (e.g., "change color to blue", "make text bigger")`}
                          className={`w-full border rounded-lg px-4 py-3 pr-12 text-sm focus:outline-none focus:border-purple-500/50 transition-colors ${darkMode
                            ? 'bg-white/5 border-white/10 text-white placeholder:text-gray-600'
                            : 'bg-gray-50 border-gray-200 text-gray-900 placeholder:text-gray-400'
                            }`}
                          autoFocus
                        />
                        <Button
                          size="icon"
                          onClick={handleElementEdit}
                          disabled={!editPrompt.trim()}
                          className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 shadow-lg"
                        >
                          <Send className="w-4 h-4" />
                        </Button>
                      </div>
                      <div className={`mt-2 text-xs transition-colors ${darkMode ? 'text-gray-500' : 'text-gray-400'}`}>
                        Selected: {selectedElement.textContent?.substring(0, 50)}
                        {selectedElement.textContent?.length > 50 && '...'}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex-1 flex min-h-0 overflow-hidden">
                {/* File Tree Sidebar */}
                <div className={`w-64 border-r flex flex-col transition-colors ${darkMode ? 'border-white/10 bg-[#0F0F14]' : 'border-gray-200 bg-gray-50'
                  }`}>
                  <div className={`p-3 border-b ${darkMode ? 'border-white/10' : 'border-gray-200'}`}>
                    <div className={`flex items-center gap-2 text-xs font-semibold uppercase tracking-wide ${darkMode ? 'text-gray-400' : 'text-gray-500'
                      }`}>
                      <Folder className="w-4 h-4" />
                      <span>Files</span>
                      <span className="ml-auto text-gray-500">{fileTree.length}</span>
                    </div>
                  </div>
                  <div className="flex-1 overflow-y-auto p-2">
                    <FileTree
                      code={fullCode}
                      darkMode={darkMode}
                      onFileSelect={(file) => setSelectedFile(file)}
                      selectedFile={selectedFile?.path}
                      projectId={currentProjectId}
                    />
                  </div>
                </div>

                {/* Code Editor */}
                <div className="flex-1 flex flex-col min-h-0 overflow-hidden min-w-0">
                  {/* File Header */}
                  <div className={`px-4 py-2 border-b flex items-center justify-between transition-colors ${darkMode ? 'border-white/10 bg-[#0F0F14]' : 'border-gray-200 bg-gray-50'
                    }`}>
                    <div className="flex items-center gap-2">
                      <File className={`w-4 h-4 ${darkMode ? 'text-gray-400' : 'text-gray-500'}`} />
                      <span className={`text-sm ${darkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                        {selectedFile?.name || 'No file selected'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500">
                        {(selectedFile?.content || previewCode).split('\n').length} lines
                      </span>
                    </div>
                  </div>

                  {/* Code Content */}
                  <div className={`flex-1 overflow-auto min-h-0 custom-scrollbar transition-colors ${darkMode ? 'bg-[#0A0A0F]' : 'bg-white'
                    }`}>
                    <div className="flex min-h-full" key={selectedFile?._loadedAt || selectedFile?.path || 'no-file'}>
                      {/* Line Numbers */}
                      <div className={`py-4 px-3 select-none border-r transition-colors ${darkMode ? 'bg-[#0A0A0F] text-gray-600 border-white/10' : 'bg-gray-50 text-gray-400 border-gray-200'
                        }`}>
                        <pre className="text-xs font-mono leading-relaxed text-right">
                          {(selectedFile?.content || previewCode).split('\n').map((_, idx) => (
                            <div key={idx}>{idx + 1}</div>
                          ))}
                        </pre>
                      </div>

                      {/* Code Content */}
                      <div className={`flex-1 py-4 px-4 overflow-x-auto custom-scrollbar min-w-0 transition-colors ${darkMode ? 'bg-[#0A0A0F]' : 'bg-white'
                        }`}>
                        <pre className={`text-sm font-mono leading-relaxed ${darkMode ? 'text-gray-300' : 'text-gray-800'}`}>
                          <code key={selectedFile?._loadedAt || selectedFile?.path || 'empty'}>
                            {selectedFile?.content || (fileTree.length > 0 ? "Select a file to view its code" : "No files generated yet")}
                          </code>
                        </pre>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Panel - Chat */}
        <ChatPanel
          messages={processedMessages}
          loading={loading}
          input={input}
          setInput={setInput}
          onSend={handleSend}
          darkMode={darkMode}
          codeVersions={branchCommits}
          selectedVersion={null}
          onLoadVersion={async (commitHash) => {
            await loadCommitCheckpoint(commitHash);
          }}
          onCopyMessage={async (text) => {
            await navigator.clipboard.writeText(text);
          }}
          onRegenerate={() => { }}
          onClearHistory={() => {
            setMessages([]);
            setPreviewCode('');
            setPreviewUrl('');
            setFileTree([]);
            setSelectedFile(null);
            setBranches([]);
            setBranchCommits([]);
          }}
          disabled={!currentProjectId}
          suggestions={(() => {
            // Get suggestions from the last assistant message, or use defaults
            const lastAssistantMsg = [...messages].reverse().find(m => m.role === 'assistant');
            return lastAssistantMsg?.suggestions || [
              'Generate a clear business case and project roadmap',
              'Create an executive dashboard for key performance metrics',
              'Analyze requirements and propose a high-level architecture',
              'Build a responsive prototype for a customer-facing app'
            ];
          })()}
          discussMode={discussMode}
          onToggleDiscuss={() => setDiscussMode(prev => !prev)}
          onExecuteTask={handleExecuteTask}
          onExecuteAllTasks={handleExecuteAllTasks}
          onEditTask={handleEditTask}
          executingTaskId={executingTaskId}
          wsConnected={wsConnected}
          onRestore={handleRestore}
          isRestoring={isRestoring}
        />
      </div>

      {/* Git Panel */}
      <GitPanel
        isVisible={showGitPanel}
        onClose={() => setShowGitPanel(false)}
        darkMode={darkMode}
        projectId={currentProjectId}
      />

      {/* Checkpoint Snackbar */}
      {showCheckpointSnackbar && viewingCheckpoint && (
        <div className="fixed bottom-6 right-6 z-50 animate-in slide-in-from-bottom duration-300">
          <div className="bg-amber-600/90 backdrop-blur-sm border border-amber-500/50 rounded-lg shadow-2xl px-4 py-3 min-w-[320px] max-w-md">
            <div className="flex items-start gap-3">
              <History className="w-5 h-5 text-amber-200 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="text-sm font-medium text-white mb-1">
                  Checkpoint Loaded
                </div>
                <div className="text-xs text-amber-100/80">
                  {viewingCheckpoint.message}
                </div>
                <div className="text-xs text-amber-200/60 mt-1">
                  {viewingCheckpoint.date}
                </div>
              </div>
              <button
                onClick={() => setShowCheckpointSnackbar(false)}
                className="text-amber-200 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;