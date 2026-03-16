import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Send, Sparkles, Code, Eye, Download, Copy, Check, Zap, RefreshCw, File, Folder, ChevronRight, ChevronDown, Plus, History, LogOut } from 'lucide-react';
import { Routes, Route, Navigate, useNavigate, Link, useParams, useLocation } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import LandingPage from './components/LandingPage';
import LoginPage from './components/LoginPage';
import SignupPage from './components/SignupPage';
import Header from './components/Header';
import GitPanel from './components/GitPanel';
import bourntecLogo from '../assets/bourntec_logo.png';
import { Button } from '@/components/ui/button';
import ChatPanel from './components/ChatPanel';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function App() {
  const { user, isAuthenticated, loading: authLoading, logout } = useAuth();
  const navigate = useNavigate();

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

  const location = useLocation();

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
        isAuthenticated ? <Navigate to="/" replace /> : <AuthLayout><LoginPage onSwitchToSignup={() => navigate('/signup')} /></AuthLayout>
      } />
      <Route path="/signup" element={
        isAuthenticated ? <Navigate to="/" replace /> : <AuthLayout><SignupPage onSwitchToLogin={() => navigate('/login')} /></AuthLayout>
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
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showProjectDropdown, setShowProjectDropdown] = useState(false);
  const [showChatHistory, setShowChatHistory] = useState(false);
  const [showGitPanel, setShowGitPanel] = useState(false);
  const [projects, setProjects] = useState([]);
  const [allChats, setAllChats] = useState([]);
  const { project_id: urlParamId } = useParams();
  
  // Determine IDs once for all state initializers
  const params = new URLSearchParams(window.location.search);
  const activeProjectId = urlParamId || params.get('project_id') || localStorage.getItem('vibecoding_workspace_id') || 'local_workspace';
  
  const [currentProjectId, setCurrentProjectId] = useState(activeProjectId);
  
  const [chatVersion, setChatVersion] = useState(() => {
    // Load current chat version for this workspace
    const saved = localStorage.getItem(`vibecoding_${activeProjectId}_version`);
    return saved ? parseInt(saved) : 1;
  });

  const [messages, setMessages] = useState(() => {
    // Load chat history for current workspace and version
    // Use the chatVersion determined above logic locally or determine it here
    const vSaved = localStorage.getItem(`vibecoding_${activeProjectId}_version`);
    const v = vSaved ? parseInt(vSaved) : 1;
    const saved = localStorage.getItem(`vibecoding_chat_${activeProjectId}_v${v}`);
    return saved ? JSON.parse(saved) : [];
  });
  
  const [codeVersions, setCodeVersions] = useState([]);
  const [currentCodeVersion, setCurrentCodeVersion] = useState(0);
  const [versionsLoaded, setVersionsLoaded] = useState(false);
  
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [previewCode, setPreviewCode] = useState('');
  const [fullCode, setFullCode] = useState(''); // Store full code for edit mode
  const [previewUrl, setPreviewUrl] = useState('');
  const [activeView, setActiveView] = useState('preview'); // preview or code
  const [copied, setCopied] = useState(false);
  const [iframeKey, setIframeKey] = useState(0);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileTree, setFileTree] = useState([]);
  const [expandedFolders, setExpandedFolders] = useState(new Set());
  const [editMode, setEditMode] = useState(false);
  const [selectedElement, setSelectedElement] = useState(null);
  const [hoveredElement, setHoveredElement] = useState(null);
  const [editPrompt, setEditPrompt] = useState('');
  const [screenSize, setScreenSize] = useState('desktop'); // desktop, tablet, mobile
  const [isDeploying, setIsDeploying] = useState(false);
  const [deployStatus, setDeployStatus] = useState(null); // 'success', 'error', or null
  const [errorHeader, setErrorHeader] = useState(null);
  const [showVersionHistory, setShowVersionHistory] = useState(false);
  const iframeRef = useRef(null);
  const prevProjectIdRef = useRef(activeProjectId);

  useEffect(() => {
    prevProjectIdRef.current = currentProjectId;
  }, [currentProjectId]);

  const fetchProjects = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/projects`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('vibecoding_token')}` }
      });
      setProjects(response.data.projects || []);
    } catch (error) {
      console.error('Failed to fetch projects:', error);
    }
  };

  // Load code versions from backend for the current project
  const loadVersionsFromBackend = async (projectId) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/projects/${projectId}/versions`);
      const backendVersions = response.data.versions || [];
      
      if (backendVersions.length > 0) {
        console.log(`📦 Found ${backendVersions.length} versions on backend for project ${projectId}`);
        
        // Convert backend versions to frontend format
        const frontendVersions = backendVersions.map((v, index) => ({
          version: index + 1,
          versionId: v.version_id,
          prompt: v.prompt || '',
          timestamp: v.created_at || new Date().toISOString(),
          code: null,       // Will be lazy-loaded when selected
          fileTree: [],
          previewUrl: ''
        }));
        
        setCodeVersions(frontendVersions);
        
        // Load the latest version's files
        const latestVersion = frontendVersions[frontendVersions.length - 1];
        try {
          const filesResp = await axios.get(`${API_BASE_URL}/api/projects/${projectId}/versions/${latestVersion.versionId}/files`);
          const filesMap = filesResp.data.files || {};
          
          // Build code string with file markers
          let fullCode = '';
          Object.entries(filesMap).forEach(([filePath, content]) => {
            fullCode += `// FILE: ${filePath}\n${content}\n\n`;
          });
          
          // Parse into file tree
          const fileTree = parseCodeToFiles(fullCode);
          
          // Update the latest version with loaded data
          setCodeVersions(prev => prev.map((v, i) => 
            i === prev.length - 1 ? { ...v, code: fullCode, fileTree } : v
          ));
          
          setCurrentCodeVersion(latestVersion.version);
          setPreviewCode(fullCode);
          setFileTree(fileTree);
          
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
          
        } catch (err) {
          console.error('Failed to load latest version files:', err);
        }
      } else {
        // No backend versions, try localStorage fallback
        const saved = localStorage.getItem(`vibecoding_code_versions_${projectId}`);
        if (saved) {
          const localVersions = JSON.parse(saved);
          setCodeVersions(localVersions);
          if (localVersions.length > 0) {
            setCurrentCodeVersion(localVersions[localVersions.length - 1].version);
          }
        }
      }
      
      setVersionsLoaded(true);
    } catch (err) {
      console.error('Failed to load versions from backend:', err);
      // Fallback to localStorage
      const saved = localStorage.getItem(`vibecoding_code_versions_${projectId}`);
      if (saved) {
        const localVersions = JSON.parse(saved);
        setCodeVersions(localVersions);
        if (localVersions.length > 0) {
          setCurrentCodeVersion(localVersions[localVersions.length - 1].version);
        }
      }
      setVersionsLoaded(true);
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
          // Attempt to create/ensure project exists on backend
          await axios.post(`${API_BASE_URL}/api/projects`, {
            project_id: urlProjectId,
            name: projectName || urlProjectId
          }, {
             headers: { Authorization: `Bearer ${localStorage.getItem('vibecoding_token')}` }
          });
          
          setCurrentProjectId(urlProjectId);
          localStorage.setItem('vibecoding_workspace_id', urlProjectId);
          projectIdToLoad = urlProjectId;
          
          // Clear URL params without reloading
          window.history.replaceState({}, '', `/a/${urlProjectId}`);
        } catch (error) {
          console.error('Failed to initialize project from URL:', error);
        }
      }
      
      fetchProjects();
      
      // Load code versions from the backend
      await loadVersionsFromBackend(projectIdToLoad);
    };

    if (isAuthenticated) {
      initProject();
    }
  }, [isAuthenticated]);

  const loadHistoricalChat = async (v) => {
    setChatVersion(v);
    localStorage.setItem(`vibecoding_${currentProjectId}_version`, v.toString());
    
    // Try to load from backend first
    try {
      const response = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/chat/v${v}`);
      if (response.data && response.data.history && response.data.history.length > 0) {
        setMessages(response.data.history);
      } else {
        // Fallback to localStorage
        const msgsStr = localStorage.getItem(`vibecoding_chat_${currentProjectId}_v${v}`);
        const msgs = msgsStr ? JSON.parse(msgsStr) : [];
        setMessages(msgs);
      }
    } catch (err) {
      console.error("Failed to load chat from backend, falling back to local storage:", err);
      const msgsStr = localStorage.getItem(`vibecoding_chat_${currentProjectId}_v${v}`);
      const msgs = msgsStr ? JSON.parse(msgsStr) : [];
      setMessages(msgs);
    }
    
    const codeVersStr = localStorage.getItem(`vibecoding_code_versions_${currentProjectId}_v${v}`);
    const codeVers = codeVersStr ? JSON.parse(codeVersStr) : [];
    setCodeVersions(codeVers);
    
    const currCodeVStr = localStorage.getItem(`vibecoding_current_code_version_${currentProjectId}_v${v}`);
    let currCodeV = currCodeVStr ? parseInt(currCodeVStr) : -1;
    if (currCodeV === -1 && codeVers.length > 0) {
      currCodeV = codeVers[codeVers.length - 1].version;
    } else if (currCodeV === -1) {
      currCodeV = 0;
    }
    setCurrentCodeVersion(currCodeV);
    
    if (codeVers.length === 0) {
        setPreviewCode('');
        setPreviewUrl('');
        setFileTree([]);
        setSelectedFile(null);
    }
    
    setShowChatHistory(false);
  };

  // Save chat history whenever messages change
  useEffect(() => {
    const saveChat = async () => {
      if (messages.length > 0 && currentProjectId === prevProjectIdRef.current) {
        try {
          // Save to backend
          await axios.post(`${API_BASE_URL}/api/projects/${currentProjectId}/chat/v${chatVersion}`, {
            history: messages
          });
          
          // Sync with local storage for backup
          localStorage.setItem(`vibecoding_chat_${currentProjectId}_v${chatVersion}`, JSON.stringify(messages));
          localStorage.setItem(`vibecoding_${currentProjectId}_version`, chatVersion.toString());
        } catch (err) {
          console.error("Failed to save chat to backend:", err);
          // Always fallback to local storage
          localStorage.setItem(`vibecoding_chat_${currentProjectId}_v${chatVersion}`, JSON.stringify(messages));
          localStorage.setItem(`vibecoding_${currentProjectId}_version`, chatVersion.toString());
        }
      }
    };
    
    if (messages.length > 0) {
      saveChat();
    }
  }, [messages, currentProjectId, chatVersion]);

  // Save code versions whenever they change
  useEffect(() => {
    // Only save if we are on the same project we started this effect with
    if (codeVersions.length > 0 && currentProjectId === prevProjectIdRef.current) {
      localStorage.setItem(`vibecoding_code_versions_${currentProjectId}`, JSON.stringify(codeVersions));
      localStorage.setItem(`vibecoding_current_code_version_${currentProjectId}`, currentCodeVersion.toString());
    }
  }, [codeVersions, currentCodeVersion, currentProjectId]);

  // Force iframe reload when preview URL changes
  useEffect(() => {
    if (previewUrl) {
      console.log('🔄 Preview URL changed, forcing iframe reload:', previewUrl);
      
      // Force iframe to reload by briefly setting to blank
      const iframe = iframeRef.current;
      if (iframe) {
        const newUrl = previewUrl;
        iframe.src = 'about:blank';
        
        // Small delay then load new URL
        setTimeout(() => {
          iframe.src = newUrl;
        }, 100);
      }
    }
  }, [previewUrl]);

  // Load code version when switching
  useEffect(() => {
    const loadAndSwitchVersion = async () => {
      if (codeVersions.length > 0 && currentCodeVersion > 0 && currentCodeVersion <= codeVersions.length) {
        let version = codeVersions[currentCodeVersion - 1];
        
        // If code is null, lazy-load it from backend
        if (version.code === null && version.versionId && currentProjectId) {
          try {
            console.log(`📥 Lazy-loading version ${version.versionId} from backend...`);
            const filesResp = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/versions/${version.versionId}/files`);
            const filesMap = filesResp.data.files || {};
            
            // Build code string with file markers
            let fullCode = '';
            Object.entries(filesMap).forEach(([filePath, content]) => {
              fullCode += `// FILE: ${filePath}\n${content}\n\n`;
            });
            
            // Parse into file tree
            const loadedFileTree = parseCodeToFiles(fullCode);
            
            // Update the version in state with loaded data
            setCodeVersions(prev => prev.map((v, i) => 
              i === currentCodeVersion - 1 ? { ...v, code: fullCode, fileTree: loadedFileTree } : v
            ));
            
            // Use loaded data directly (don't wait for state update)
            version = { ...version, code: fullCode, fileTree: loadedFileTree };
          } catch (err) {
            console.error('Failed to lazy-load version from backend:', err);
          }
        }
        
        setPreviewCode(version.code || '');
        setFileTree(version.fileTree || []);
        
        // Trigger version switch in container
        if (version.versionId && currentProjectId) {
          // Switch git checkpoint internally
          axios.post(`${API_BASE_URL}/api/git/checkpoint`, {
            project_id: currentProjectId,
            version_id: version.versionId
          }).catch(err => console.error('Failed to switch git checkpoint:', err));

          axios.post(`${API_BASE_URL}/api/projects/${currentProjectId}/versions/${version.versionId}/preview`)
            .then(response => {
              const newPreviewUrl = response.data.preview_url;
              // Add cache-busting parameter to force iframe reload
              const separator = newPreviewUrl.includes('?') ? '&' : '?';
              const urlWithVersion = `${newPreviewUrl}${separator}v=${version.versionId}&t=${Date.now()}`;
              setPreviewUrl(urlWithVersion);
              console.log(`🔄 Switched to version ${version.versionId}: ${urlWithVersion}`);
            })
            .catch(error => {
              console.error('Failed to switch version:', error);
              // Fallback to stored URL
              const baseUrl = version.previewUrl || '';
              if (baseUrl) {
                const separator = baseUrl.includes('?') ? '&' : '?';
                const urlWithVersion = `${baseUrl}${separator}v=${version.versionId}&t=${Date.now()}`;
                setPreviewUrl(urlWithVersion);
              } else {
                setPreviewUrl('');
              }
            });
        } else {
          // No version ID, use stored URL
          const baseUrl = version.previewUrl || '';
          if (baseUrl) {
            const separator = baseUrl.includes('?') ? '&' : '?';
            const urlWithVersion = `${baseUrl}${separator}v=${version.versionId}&t=${Date.now()}`;
            setPreviewUrl(urlWithVersion);
          } else {
            setPreviewUrl('');
          }
        }
        
        if (version.fileTree && version.fileTree.length > 0) {
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
          const firstFile = findFirstFile(version.fileTree);
          if (firstFile) setSelectedFile(firstFile);
        }
        setIframeKey(prev => prev + 1);
      }
    };
    
    loadAndSwitchVersion();
    
    // Also load chat history for this version if it exists
    if (currentCodeVersion > 0 && currentCodeVersion <= codeVersions.length) {
      const version = codeVersions[currentCodeVersion - 1];
      if (version && version.versionId) {
        axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/chat/${version.versionId}`)
          .then(response => {
            if (response.data && response.data.history && response.data.history.length > 0) {
              setMessages(response.data.history);
            }
          })
          .catch(err => console.error("Failed to load chat for version:", err));
      }
    }
  }, [currentCodeVersion]);

  // Reload iframe when previewUrl changes
  useEffect(() => {
    if (previewUrl) {
      console.log('🔄 Preview URL changed, reloading iframe:', previewUrl);
      setIframeKey(prev => prev + 1);
    }
  }, [previewUrl]);

  // Function to save a new code version
  const saveCodeVersion = (code, previewUrl, fileTree, prompt, backendVersionId = null) => {
    const newVersion = {
      version: codeVersions.length + 1,
      versionId: backendVersionId,
      code,
      previewUrl,
      fileTree,
      prompt,
      timestamp: new Date().toISOString()
    };
    setCodeVersions(prev => [...prev, newVersion]);
    setCurrentCodeVersion(newVersion.version);
  };

  // Function to start a new chat
  const handleNewChat = async () => {
    // If there is current code that isn't saved as a version, save it first
    if (previewCode && codeVersions.length === 0) {
      saveCodeVersion(previewCode, previewUrl, fileTree, 'Snapshot before new chat');
    }

    const newVersion = chatVersion + 1;
    setChatVersion(newVersion);
    setMessages([]);
    // Do NOT clear codeVersions or previewCode - they are project-wide history now
      setEditMode(false);
      setSelectedElement(null);
      localStorage.setItem(`vibecoding_${currentProjectId}_version`, newVersion.toString());

      // Create a new Git branch for this chat session
      try {
        await axios.post(`${API_BASE_URL}/api/chat/new`, {
          project_id: currentProjectId,
          chat_version: newVersion
        });
        console.log(`🌿 Created new git branch for chat v${newVersion}`);
        // Refresh versions list from backend
        await loadVersionsFromBackend(currentProjectId);
      } catch (err) {
        console.error('Failed to create new git branch:', err);
      }
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
            className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors ${
              selectedFile?.path === item.path
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

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = { role: 'user', content: input, timestamp: new Date().toISOString() };
    setMessages(prev => [...prev, userMessage]);
    const currentInput = input;
    setInput('');
    setLoading(true);

    try {
      const response = await axios.post(`${API_BASE_URL}/api/generate`, {
        prompt: currentInput,
        history: messages,
        project_id: currentProjectId
      });

      const aiMessage = {
        role: 'assistant',
        content: response.data.message,
        code: response.data.code,
        versionId: response.data.version_id,
        toolCalls: response.data.tool_calls_log || null,
        timestamp: new Date().toISOString()
      };

      setMessages(prev => [...prev, aiMessage]);
      
      if (response.data.code) {
        const fullCodeContent = response.data.code;
        setFullCode(fullCodeContent); // Store full code
        setPreviewCode(fullCodeContent);
        setIframeKey(prev => prev + 1); // Force iframe refresh
        
        // Parse code to build file tree
        const code = fullCodeContent;
        const files = parseCodeToFiles(code);
        setFileTree(files);
        
        // We no longer save a new folder version for every chat message (git commits instead)
        // saveCodeVersion(code, response.data.preview_url || '', files, currentInput, response.data.version_id);
        
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
          // First, look for preview.html (standalone preview)
          for (const item of items) {
            if (item.type === 'file' && (item.name === 'preview.html' || item.path.endsWith('/preview.html'))) {
              return item.content;
            }
            if (item.type === 'folder' && item.children) {
              const found = findPreviewHtmlFile(item.children);
              if (found) return found;
            }
          }
          
          // If no preview.html, look for any HTML file
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
          // Found HTML file, use it for preview display
          setPreviewCode(htmlContent);
        } else if (files.length === 1 && files[0].type === 'file') {
          // Single file, use its content
          setPreviewCode(files[0].content);
        }
        // Otherwise keep the full code for preview
      }
      
      if (response.data.preview_url) {
        console.log('🌐 Container preview:', response.data.preview_url);
        setPreviewUrl(response.data.preview_url);
        setActiveView('preview');
      } else if (response.data.code) {
        // No container URL, use inline preview
        setPreviewUrl('');
        setActiveView('preview');
      }
    } catch (error) {
      console.error('Error:', error);
      const errorMessage = error.response?.data?.detail || error.message || 'Sorry, there was an error. Please try again.';
      setErrorHeader(errorMessage);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `I encountered an error while generating or deploying the preview: ${errorMessage}`,
        timestamp: new Date().toISOString()
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleDeploy = async () => {
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
    setIframeKey(prev => prev + 1);
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

  // Track iframe container ref for overlay positioning
  const iframeContainerRef = useRef(null);

  // Listen for postMessage events from iframe
  useEffect(() => {
    const handleMessage = (event) => {
      const msg = event.data;
      if (!msg || !msg.type) return;

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
        const menuY = iframeRect.top  + (msg.data.mouseY || msg.data.rect.top);
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
      iframe.contentWindow.postMessage({ type: 'set-edit-mode', value: editMode }, '*');
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
        toolCalls: response.data.tool_calls_log || null,
        timestamp: new Date().toISOString()
      };

      setMessages(prev => [...prev, aiMessage]);
      
      if (response.data.code) {
        const fullCodeContent = response.data.code;
        setFullCode(fullCodeContent);
        setPreviewCode(fullCodeContent);
        setIframeKey(prev => prev + 1);
        
        const code = fullCodeContent;
        const files = parseCodeToFiles(code);
        setFileTree(files);
        
        // Save this as a new code version
        saveCodeVersion(code, response.data.preview_url || '', files, editMessage.content);
        
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
      
      if (response.data.preview_url) {
        setPreviewUrl(response.data.preview_url);
      }
      
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
      // Multi-file structure
      const files = [];
      
      for (let i = 0; i < matches.length; i++) {
        const match = matches[i];
        const filename = (match[1] || match[2] || match[3]).trim();
        const startPos = match.index + match[0].length;
        const endPos = i < matches.length - 1 ? matches[i + 1].index : code.length;
        const content = code.substring(startPos, endPos).trim();
        
        files.push({
          name: filename.split('/').pop(),
          path: filename,
          content: content,
          type: 'file'
        });
      }
      
      // Build tree structure from flat file list
      return buildFileTree(files);
    } else {
      // Single file - detect type
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
    // Last resort: fullCode (may be single-file HTML or raw code)
    return fullCode || previewCode || '';
  };

  return (
    <div className="h-screen flex flex-col bg-[#0A0A0F] text-white">
      <Header 
        chatVersion={`v${chatVersion}`}
        user={user}
        showUserMenu={showUserMenu}
        setShowUserMenu={setShowUserMenu}
        projects={projects}
        currentProjectId={currentProjectId}
        setCurrentProjectId={setCurrentProjectId}
        showProjectDropdown={showProjectDropdown}
        setShowProjectDropdown={setShowProjectDropdown}
        onNewChat={handleNewChat}
        onGitClick={() => setShowGitPanel(true)}
        onDeploy={handleDeploy}
        isDeploying={isDeploying}
        deployStatus={deployStatus}
        previewCode={previewCode}
        loading={loading}
        onLogout={logout}
        codeVersions={codeVersions}
        currentCodeVersion={currentCodeVersion}
        setCurrentCodeVersion={setCurrentCodeVersion}
        formatTimestamp={formatTimestamp}
      />



      {/* Error/Status Banner */}
      {(errorHeader || deployStatus === 'success') && (
        <div className={`h-10 flex items-center justify-center px-6 text-sm animate-in slide-in-from-top duration-300 ${
          deployStatus === 'success' ? 'bg-green-600/20 text-green-300' : 'bg-red-600/20 text-red-300'
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
          <div className="h-12 border-b border-white/10 flex items-center justify-between px-4 bg-[#0F0F14] sticky top-0 z-10">
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setActiveView('preview')}
                className={`${
                  activeView === 'preview'
                    ? 'bg-white/10 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <Eye className="w-4 h-4 inline mr-2" />
                Preview
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setActiveView('code')}
                className={`${
                  activeView === 'code'
                    ? 'bg-white/10 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <Code className="w-4 h-4 inline mr-2" />
                Code
              </Button>
            </div>

            
            {previewCode && activeView === 'preview' && (
              <div className="flex items-center gap-2">
                {/* Screen Size Selector */}
                <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-white/5">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setScreenSize('mobile')}
                    className={`h-8 w-8 ${
                      screenSize === 'mobile' ? 'bg-white/20 text-white' : 'text-gray-400 hover:text-white'
                    }`}
                    title="Mobile (375px)"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <rect x="7" y="2" width="10" height="20" rx="2" strokeWidth="2"/>
                    </svg>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setScreenSize('tablet')}
                    className={`h-8 w-8 ${
                      screenSize === 'tablet' ? 'bg-white/20 text-white' : 'text-gray-400 hover:text-white'
                    }`}
                    title="Tablet (768px)"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <rect x="4" y="3" width="16" height="18" rx="2" strokeWidth="2"/>
                    </svg>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setScreenSize('desktop')}
                    className={`h-8 w-8 ${
                      screenSize === 'desktop' ? 'bg-white/20 text-white' : 'text-gray-400 hover:text-white'
                    }`}
                    title="Desktop (100%)"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <rect x="2" y="4" width="20" height="12" rx="2" strokeWidth="2"/>
                      <path d="M8 20h8" strokeWidth="2"/>
                      <path d="M12 16v4" strokeWidth="2"/>
                    </svg>
                  </Button>
                </div>

                {/* Edit Mode Toggle */}
                <Button
                  variant={editMode ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setEditMode(!editMode)}
                  className={`${
                    editMode 
                      ? 'bg-purple-600 text-white hover:bg-purple-700' 
                      : 'bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white'
                  }`}
                  title="Edit Mode - Click elements to edit"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                  {editMode ? 'Editing' : 'Edit'}
                </Button>
                
                <div className="h-6 w-px bg-white/10" />
                
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleRefresh}
                  className="bg-white/5 hover:bg-white/10"
                  title="Refresh Preview"
                >
                  <RefreshCw className="w-4 h-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCopy}
                  className="bg-white/5 hover:bg-white/10"
                >
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  {copied ? 'Copied' : 'Copy'}
                </Button>
                <Button 
                  variant="ghost"
                  size="sm"
                  onClick={handleDownload}
                  className="bg-white/5 hover:bg-white/10"
                >
                  <Download className="w-4 h-4" />
                  Download
                </Button>
              </div>
            )}
            
            {previewCode && activeView === 'code' && (
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCopy}
                  className="bg-white/5 hover:bg-white/10"
                >
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  {copied ? 'Copied' : 'Copy'}
                </Button>
                <Button 
                  variant="ghost"
                  size="sm"
                  onClick={handleDownload}
                  className="bg-white/5 hover:bg-white/10"
                >
                  <Download className="w-4 h-4" />
                  Download
                </Button>
              </div>
            )}
          </div>

          {/* Content Area */}
          <div className="flex-1 relative bg-[#0A0A0F] overflow-hidden min-h-0 flex flex-col">
            {!previewCode ? (
              <div className="h-full flex items-center justify-center">
                <div className="text-center">
                  <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 flex items-center justify-center mx-auto mb-4">
                    <Sparkles className="w-10 h-10 text-purple-400" />
                  </div>
                  <h3 className="text-xl font-semibold mb-2">No Preview Yet</h3>
                  <p className="text-gray-400">Start chatting to generate your app</p>
                </div>
              </div>
            ) : activeView === 'preview' ? (
              <div className="h-full flex flex-col">
                {/* Browser-like URL Bar */}
                <div className="flex-shrink-0 border-b border-white/10 bg-[#0F0F14]">
                  <div className="flex items-center gap-2 px-4 py-2">
                    <Button 
                      variant="ghost"
                      size="icon"
                      onClick={handleRefresh}
                      className="h-8 w-8 hover:bg-white/10"
                      title="Refresh"
                    >
                      <RefreshCw className="w-4 h-4 text-gray-400" />
                    </Button>
                    <div className="flex-1 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#1e1e1e] border border-white/10">
                      <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                      </svg>
                      <input
                        type="text"
                        value={previewUrl || 'your-app.vibecoding.app'}
                        readOnly
                        className="flex-1 bg-transparent text-sm outline-none text-gray-300"
                      />
                      {previewUrl && (
                        <Button
                          variant="default"
                          size="sm"
                          onClick={() => window.open(previewUrl, '_blank')}
                          className="h-6 px-2 text-xs bg-blue-600 text-white hover:bg-blue-700"
                        >
                          Open
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
                
                {/* Edit Mode Banner */}
                {editMode && (
                  <div className="flex-shrink-0 bg-purple-600/20 border-b border-purple-500/30 px-4 py-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-sm text-purple-200">
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
                
                {/* Preview iframe with responsive sizing */}
                {/* The iframe source NEVER changes when toggle edit mode.
                    Editor script is always injected into srcDoc; it stays dormant until activated. */}
                <div 
                  className={`flex-1 relative flex items-center justify-center bg-[#0A0A0F]`}
                >
                  <div 
                    className={`h-full transition-all duration-300 relative ${
                      screenSize === 'mobile' ? 'w-[375px]' :
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
                        // Notify injected script of current edit mode state after (re)load
                        const iframe = iframeRef.current;
                        if (iframe && iframe.contentWindow) {
                          iframe.contentWindow.postMessage({ type: 'set-edit-mode', value: editMode }, '*');
                        }
                      }}
                    />

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
                          {['tl','tr','bl','br'].map(c => (
                            <div key={c} className={`absolute w-2.5 h-2.5 bg-violet-500 rounded-sm border border-white ${
                              c==='tl' ? '-top-1.5 -left-1.5' : c==='tr' ? '-top-1.5 -right-1.5' : c==='bl' ? '-bottom-1.5 -left-1.5' : '-bottom-1.5 -right-1.5'
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
                  <div className="flex-shrink-0 border-t border-white/10 bg-[#0F0F14] p-4">
                    <div className="max-w-4xl mx-auto">
                      <div className="mb-2 flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm text-gray-400">
                          <span className="px-2 py-0.5 rounded bg-purple-600/20 text-purple-300 font-mono text-xs">
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
                          className="h-8 w-8 text-gray-400 hover:text-white"
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
                          className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 pr-12 text-sm focus:outline-none focus:border-purple-500/50 transition-colors"
                          autoFocus
                        />
                        <Button
                          size="icon"
                          onClick={handleElementEdit}
                          disabled={!editPrompt.trim()}
                          className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700"
                        >
                          <Send className="w-4 h-4" />
                        </Button>
                      </div>
                      <div className="mt-2 text-xs text-gray-500">
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
                <div className="w-64 border-r border-white/10 bg-[#0F0F14] overflow-y-auto">
                  <div className="p-3 border-b border-white/10">
                    <div className="flex items-center gap-2 text-xs font-semibold text-gray-400 uppercase tracking-wide">
                      <Folder className="w-4 h-4" />
                      <span>Files</span>
                      <span className="ml-auto text-gray-500">{fileTree.length}</span>
                    </div>
                  </div>
                  <div className="p-2">
                    {renderFileTree(fileTree)}
                  </div>
                </div>

                {/* Code Editor */}
                <div className="flex-1 flex flex-col min-h-0 overflow-hidden min-w-0">
                  {/* File Header */}
                  <div className="px-4 py-2 border-b border-white/10 bg-[#0F0F14] flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <File className="w-4 h-4 text-gray-400" />
                      <span className="text-sm text-gray-300">
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
                  <div className="flex-1 overflow-auto min-h-0 custom-scrollbar">
                    <div className="flex min-h-full">
                      {/* Line Numbers */}
                      <div className="py-4 px-3 select-none bg-[#0A0A0F] text-gray-600 border-r border-white/10">
                        <pre className="text-xs font-mono leading-relaxed text-right">
                          {(selectedFile?.content || previewCode).split('\n').map((_, idx) => (
                            <div key={idx}>{idx + 1}</div>
                          ))}
                        </pre>
                      </div>
                      
                      {/* Code Content */}
                      <div className="flex-1 py-4 px-4 overflow-x-auto custom-scrollbar bg-[#0A0A0F] min-w-0">
                        <pre className="text-sm font-mono leading-relaxed text-gray-300">
                          <code>{selectedFile?.content || previewCode}</code>
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
          messages={messages}
          loading={loading}
          input={input}
          setInput={setInput}
          onSend={handleSend}
          onKeyPress={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          darkMode={true}
          codeVersions={codeVersions}
          selectedVersion={currentCodeVersion}
          onLoadVersion={async (versionId) => {
            setCurrentCodeVersion(versionId);
            try {
              // Try to checkout the checkpoint via git
              const response = await axios.post(`${API_BASE_URL}/api/git/checkpoint`, {
                project_id: currentProjectId,
                version_id: versionId
              });
              
              if (response.data.status === 'success') {
                // After successful checkout, refresh files from the workspace
                const filesResp = await axios.get(`${API_BASE_URL}/api/projects/${currentProjectId}/versions/workspace/files`);
                const filesMap = filesResp.data.files || {};
                
                let fullCodeStr = '';
                Object.entries(filesMap).forEach(([filePath, content]) => {
                  fullCodeStr += `// FILE: ${filePath}\n${content}\n\n`;
                });
                
                const files = parseCodeToFiles(fullCodeStr);
                setFileTree(files);
                setPreviewCode(fullCodeStr);
                setIframeKey(prev => prev + 1);
              }
            } catch (err) {
              console.error('Failed to load checkpoint:', err);
            }
          }}
          onCopyMessage={async (text) => {
            await navigator.clipboard.writeText(text);
          }}
          onRegenerate={() => {}}
          onClearHistory={() => {
            setMessages([]);
            setPreviewCode('');
            setPreviewUrl('');
            setFileTree([]);
            setSelectedFile(null);
            setCodeVersions([]);
            setCurrentCodeVersion(0);
          }}
          suggestions={[
            'Create a beautiful landing page with gradient background',
            'Build a todo app with Flask backend',
            'Create a calculator app'
          ]}
        />
      </div>

      {/* Git Panel */}
      <GitPanel
        isVisible={showGitPanel}
        onClose={() => setShowGitPanel(false)}
        darkMode={true}
        projectId={currentProjectId}
      />
    </div>
  );
}

export default App;
