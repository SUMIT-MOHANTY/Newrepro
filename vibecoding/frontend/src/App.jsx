import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Send, Sparkles, Code, Eye, Download, Copy, Check, Zap, RefreshCw, File, Folder, ChevronRight, ChevronDown, Plus, History } from 'lucide-react';
import { Button } from '@/components/ui/button';
import ChatPanel from './components/ChatPanel';
import CodePreview from './components/CodePreview';
import GitPanel from './components/GitPanel';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function App() {
  const [currentProjectId, setCurrentProjectId] = useState(() => {
    // Load or create workspace ID
    const saved = localStorage.getItem('vibecoding_workspace_id');
    if (saved) return saved;
    const newId = `workspace_${Date.now()}`;
    localStorage.setItem('vibecoding_workspace_id', newId);
    return newId;
  });
  
  const [chatVersion, setChatVersion] = useState(() => {
    // Load current chat version for this workspace
    const saved = localStorage.getItem(`vibecoding_${currentProjectId}_version`);
    return saved ? parseInt(saved) : 1;
  });

  const [messages, setMessages] = useState(() => {
    // Load chat history for current workspace and version
    const saved = localStorage.getItem(`vibecoding_chat_${currentProjectId}_v${chatVersion}`);
    return saved ? JSON.parse(saved) : [];
  });
  
  const [codeVersions, setCodeVersions] = useState(() => {
    // Load code versions for current chat
    const saved = localStorage.getItem(`vibecoding_code_versions_${currentProjectId}_v${chatVersion}`);
    return saved ? JSON.parse(saved) : [];
  });
  
  const [currentCodeVersion, setCurrentCodeVersion] = useState(() => {
    const saved = localStorage.getItem(`vibecoding_current_code_version_${currentProjectId}_v${chatVersion}`);
    return saved ? parseInt(saved) : 0;
  });
  
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
  const [showGitPanel, setShowGitPanel] = useState(false);
  const iframeRef = useRef(null);

  // Save chat history whenever messages change
  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem(`vibecoding_chat_${currentProjectId}_v${chatVersion}`, JSON.stringify(messages));
      localStorage.setItem(`vibecoding_${currentProjectId}_version`, chatVersion.toString());
    }
  }, [messages, currentProjectId, chatVersion]);

  // Save code versions whenever they change
  useEffect(() => {
    if (codeVersions.length > 0) {
      localStorage.setItem(`vibecoding_code_versions_${currentProjectId}_v${chatVersion}`, JSON.stringify(codeVersions));
      localStorage.setItem(`vibecoding_current_code_version_${currentProjectId}_v${chatVersion}`, currentCodeVersion.toString());
    }
  }, [codeVersions, currentCodeVersion, currentProjectId, chatVersion]);

  // Load code version when switching
  useEffect(() => {
    if (codeVersions.length > 0 && currentCodeVersion > 0 && currentCodeVersion <= codeVersions.length) {
      const version = codeVersions[currentCodeVersion - 1];
      setPreviewCode(version.code);
      setPreviewUrl(version.previewUrl || '');
      setFileTree(version.fileTree || []);
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
  }, [currentCodeVersion]);

  // Function to save a new code version
  const saveCodeVersion = (code, previewUrl, fileTree, prompt) => {
    const newVersion = {
      version: codeVersions.length + 1,
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
  const handleNewChat = () => {
    const newVersion = chatVersion + 1;
    setChatVersion(newVersion);
    setMessages([]);
    setPreviewCode('');
    setPreviewUrl('');
    setFileTree([]);
    setSelectedFile(null);
    setEditMode(false);
    setSelectedElement(null);
    setCodeVersions([]);
    setCurrentCodeVersion(0);
    localStorage.setItem(`vibecoding_${currentProjectId}_version`, newVersion.toString());
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

      console.log('🔍 API Response:', response.data);

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
        setFullCode(fullCodeContent); // Store full code
        setPreviewCode(fullCodeContent);
        setIframeKey(prev => prev + 1); // Force iframe refresh
        
        // Parse code to build file tree
        const code = fullCodeContent;
        const files = parseCodeToFiles(code);
        setFileTree(files);
        
        // Save this as a new code version
        saveCodeVersion(code, response.data.preview_url || '', files, currentInput);
        
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
    a.download = 'code.html';
    a.click();
    URL.revokeObjectURL(url);
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
        if (e.data && e.data.type === 'set-edit-mode') {
          editMode = e.data.value;
          if (!editMode) {
            clearHover();
            clearSelection();
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
        window.parent.postMessage({ type: 'element-selected', data: getElementInfo(el) }, '*');
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
        setSelectedElement({
          ...msg.data,
          rect: {
            top: msg.data.rect.top + offsetTop,
            left: msg.data.rect.left + offsetLeft,
            width: msg.data.rect.width,
            height: msg.data.rect.height,
          }
        });
      } else if (msg.type === 'element-deselect') {
        setSelectedElement(null);
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
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showVersionHistory]);

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
      {/* Top Header - Base44 Style */}
      <div className="h-14 border-b border-white/10 flex items-center justify-between px-6 bg-[#0F0F14]">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
              <Zap className="w-5 h-5" />
            </div>
            <span className="font-bold text-lg">VibeCoding</span>
          </div>
          <div className="h-6 w-px bg-white/10" />
          <span className="text-sm text-gray-400">Chat v{chatVersion}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button 
            variant="ghost"
            size="sm"
            onClick={handleNewChat}
            className="bg-white/5 hover:bg-white/10"
            title="Start a new chat"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </Button>
          <Button 
            variant="ghost"
            size="sm"
            onClick={() => setShowGitPanel(true)}
            className="bg-white/5 hover:bg-white/10"
            title="Git Integration"
          >
            <History className="w-4 h-4" />
            Git
          </Button>
          <Button 
            disabled={isDeploying || !previewCode}
            onClick={handleDeploy}
            className={`transition-all duration-300 ${
              deployStatus === 'success' ? 'bg-green-600 hover:bg-green-700' :
              deployStatus === 'error' ? 'bg-red-600 hover:bg-red-700' :
              'bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700'
            } text-sm font-medium min-w-[100px] flex items-center justify-center gap-2`}
          >
            {isDeploying ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : deployStatus === 'success' ? (
              <Check className="w-4 h-4" />
            ) : deployStatus === 'error' ? (
              <Zap className="w-4 h-4" />
            ) : null}
            {isDeploying ? 'Deploying...' : 
             deployStatus === 'success' ? 'Deployed!' : 
             deployStatus === 'error' ? 'Failed' : 'Deploy'}
          </Button>
        </div>
      </div>

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
        <div className="flex-1 flex flex-col min-w-0">
          <CodePreview
            previewCode={fullCode || previewCode}
            activeTab={activeView}
            setActiveTab={setActiveView}
            darkMode={true}
            copied={copied}
            onCopyCode={handleCopy}
            onRefreshPreview={handleRefresh}
            onDownloadCode={handleDownload}
            codeVersions={codeVersions.map(v => ({ id: v.version, timestamp: v.timestamp }))}
            selectedVersion={currentCodeVersion}
            onLoadVersion={(id) => setCurrentCodeVersion(id)}
            containerPreviewUrl={previewUrl}
          />
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
          onLoadVersion={(versionId) => {
            setCurrentCodeVersion(versionId);
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

      <GitPanel 
        isVisible={showGitPanel}
        onClose={() => setShowGitPanel(false)}
        projectId={currentProjectId}
        darkMode={true}
      />
    </div>
  );
}

export default App;
