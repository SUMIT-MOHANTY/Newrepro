import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Send, Sparkles, Code, Eye, Download, Copy, Check, Zap, RefreshCw, File, Folder, ChevronRight, ChevronDown, Plus, History } from 'lucide-react';
import { Button } from '@/components/ui/button';
import ChatPanel from './components/ChatPanel';

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
  const [editPrompt, setEditPrompt] = useState('');
  const [screenSize, setScreenSize] = useState('desktop'); // desktop, tablet, mobile
  const [showVersionHistory, setShowVersionHistory] = useState(false);

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
      const response = await axios.post('http://localhost:8000/api/generate', {
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
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, there was an error. Please try again.',
        timestamp: new Date().toISOString()
      }]);
    } finally {
      setLoading(false);
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

  // Listen for element selection from iframe
  useEffect(() => {
    const handleMessage = (event) => {
      if (event.data.type === 'element-selected') {
        setSelectedElement(event.data);
      }
    };
    
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

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

  // Inject edit mode script when editMode changes
  useEffect(() => {
    if (!editMode) {
      setSelectedElement(null);
    }
    // Don't force iframe reload - let React handle it naturally
  }, [editMode]);

  // Prepare preview code with edit mode script injected
  const getPreviewContent = () => {
    // Use fullCode for edit mode to preserve all styles and structure
    const codeToUse = fullCode || previewCode;
    if (!codeToUse) return '';
    
    if (!editMode) return codeToUse;

    // Inject edit mode script into the HTML
    const editModeScript = `
      <style id="vibe-edit-style">
        * {
          cursor: crosshair !important;
        }
        .vibe-edit-hover {
          outline: 3px solid #a855f7 !important;
          outline-offset: 2px !important;
          box-shadow: 0 0 0 3px rgba(168, 85, 247, 0.2) !important;
          position: relative !important;
          z-index: 999999 !important;
        }
        .vibe-edit-selected {
          outline: 4px solid #8b5cf6 !important;
          outline-offset: 2px !important;
          background: rgba(168, 85, 247, 0.15) !important;
          box-shadow: 0 0 0 4px rgba(139, 92, 246, 0.3) !important;
          position: relative !important;
          z-index: 999999 !important;
        }
      </style>
      <script id="vibe-edit-script">
        (function() {
          console.log('🎨 Edit mode script loaded');
          let currentHover = null;
          let isInitialized = false;
          
          function initEditMode() {
            if (isInitialized) {
              console.log('⚠️ Edit mode already initialized');
              return;
            }
            
            console.log('✅ Initializing edit mode handlers');
            isInitialized = true;
            
            // Prevent default link behavior
            document.addEventListener('click', function(e) {
              if (e.target.tagName === 'A') {
                e.preventDefault();
              }
            }, true);
            
            // Hover effect - use capture phase
            document.addEventListener('mouseover', function(e) {
              e.stopPropagation();
              const target = e.target;
              
              if (!target || target.tagName === 'HTML' || target.tagName === 'BODY' || 
                  target.tagName === 'SCRIPT' || target.tagName === 'STYLE' ||
                  target.id === 'vibe-edit-style' || target.id === 'vibe-edit-script') {
                return;
              }
              
              if (currentHover && currentHover !== target) {
                currentHover.classList.remove('vibe-edit-hover');
              }
              
              target.classList.add('vibe-edit-hover');
              currentHover = target;
              console.log('👆 Hovering:', target.tagName, target.className);
            }, true);
            
            document.addEventListener('mouseout', function(e) {
              e.stopPropagation();
              const target = e.target;
              if (target && target.tagName !== 'HTML' && target.tagName !== 'BODY') {
                target.classList.remove('vibe-edit-hover');
              }
            }, true);
            
            // Click to select - use capture phase
            document.addEventListener('click', function(e) {
              const target = e.target;
              
              if (!target || target.tagName === 'HTML' || target.tagName === 'BODY' || 
                  target.tagName === 'SCRIPT' || target.tagName === 'STYLE') {
                return;
              }
              
              e.preventDefault();
              e.stopPropagation();
              
              console.log('🎯 Element clicked:', target.tagName, target.className);
              
              // Remove previous selection highlights
              document.querySelectorAll('.vibe-edit-selected').forEach(function(el) {
                el.classList.remove('vibe-edit-selected');
              });
              
              // Highlight clicked element
              target.classList.add('vibe-edit-selected');
              target.classList.remove('vibe-edit-hover');
              
              // Get clean className without edit classes
              const cleanClassName = target.className
                .replace(/vibe-edit-hover/g, '')
                .replace(/vibe-edit-selected/g, '')
                .trim();
              
              // Send element info to parent
              try {
                window.parent.postMessage({
                  type: 'element-selected',
                  tagName: target.tagName,
                  className: cleanClassName,
                  id: target.id || '',
                  textContent: (target.textContent || '').substring(0, 100),
                  innerHTML: (target.innerHTML || '').substring(0, 200)
                }, '*');
                console.log('📤 Message sent to parent');
              } catch (err) {
                console.error('❌ Error sending message:', err);
              }
            }, true);
            
            console.log('✨ Edit mode ready!');
          }
          
          // Try multiple initialization methods
          if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initEditMode);
            console.log('⏳ Waiting for DOMContentLoaded');
          } else {
            console.log('⚡ DOM already loaded, initializing immediately');
            initEditMode();
          }
          
          // Backup: also try on window load
          window.addEventListener('load', function() {
            console.log('🔄 Window loaded, ensuring edit mode is initialized');
            initEditMode();
          });
          
          // Immediate attempt
          setTimeout(initEditMode, 100);
        })();
      </script>
    `;

    // Inject before closing </body> tag, or before </html> if no body, or at the end
    let modifiedCode = codeToUse;
    if (modifiedCode.toLowerCase().includes('</body>')) {
      modifiedCode = modifiedCode.replace(/<\/body>/i, editModeScript + '</body>');
    } else if (modifiedCode.toLowerCase().includes('</html>')) {
      modifiedCode = modifiedCode.replace(/<\/html>/i, editModeScript + '</html>');
    } else {
      // No closing tags found, append at the end
      modifiedCode = modifiedCode + editModeScript;
    }
    
    return modifiedCode;
  };

  // Handle element edit
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
      const response = await axios.post('http://localhost:8000/api/generate', {
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
          {codeVersions.length > 0 && (
            <>
              <div className="h-6 w-px bg-white/10" />
              <div className="relative version-history-container">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowVersionHistory(!showVersionHistory)}
                  className="flex items-center gap-2 bg-white/5 hover:bg-white/10"
                >
                  <History className="w-4 h-4" />
                  <span>Code v{currentCodeVersion}/{codeVersions.length}</span>
                </Button>
                
                {/* Version History Dropdown */}
                {showVersionHistory && (
                  <div className="absolute top-full left-0 mt-2 w-80 bg-[#1a1a1f] border border-white/10 rounded-lg shadow-xl z-50 max-h-96 overflow-y-auto">
                    <div className="p-3 border-b border-white/10">
                      <div className="text-sm font-semibold text-white">Code Version History</div>
                      <div className="text-xs text-gray-400 mt-1">{codeVersions.length} versions saved</div>
                    </div>
                    <div className="p-2">
                      {codeVersions.map((version) => (
                        <Button
                          key={version.version}
                          variant="ghost"
                          onClick={() => {
                            setCurrentCodeVersion(version.version);
                            setShowVersionHistory(false);
                          }}
                          className={`w-full text-left px-3 py-2 h-auto rounded-lg mb-1 ${
                            currentCodeVersion === version.version
                              ? 'bg-purple-600/20 border border-purple-500/30'
                              : 'hover:bg-white/5'
                          }`}
                        >
                          <div className="w-full">
                            <div className="flex items-center justify-between mb-1">
                              <span className={`text-sm font-medium ${
                                currentCodeVersion === version.version ? 'text-purple-300' : 'text-white'
                              }`}>
                                Version {version.version}
                              </span>
                              <span className="text-xs text-gray-500">
                                {formatTimestamp(version.timestamp)}
                              </span>
                            </div>
                            <div className="text-xs text-gray-400 line-clamp-2">
                              {version.prompt}
                            </div>
                          </div>
                        </Button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
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
          <Button className="bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-sm font-medium">
            Deploy
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Right Panel - Preview/Code */}
        <div className="flex-1 flex flex-col">
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
          <div className="flex-1 relative bg-[#0A0A0F]">
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
                    <div className="flex items-center gap-2 text-sm text-purple-200">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span>Edit Mode Active - Click any element in the preview to edit it</span>
                    </div>
                  </div>
                )}
                
                {/* Preview iframe with responsive sizing */}
                <div className={`flex-1 relative flex items-center justify-center ${editMode ? 'bg-white' : 'bg-[#0A0A0F]'}`}>
                  <div 
                    className={`h-full transition-all duration-300 ${
                      screenSize === 'mobile' ? 'w-[375px]' :
                      screenSize === 'tablet' ? 'w-[768px]' :
                      'w-full'
                    }`}
                    style={{
                      boxShadow: screenSize !== 'desktop' ? (editMode ? '0 0 0 1px rgba(0,0,0,0.1)' : '0 0 0 1px rgba(255,255,255,0.1)') : 'none'
                    }}
                  >
                    <iframe
                      key={iframeKey}
                      src={previewUrl || `data:text/html;charset=utf-8,${encodeURIComponent(editMode ? getPreviewContent() : (fullCode || previewCode))}`}
                      className="w-full h-full border-0"
                      title="Preview"
                      sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                    />
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
              <div className="h-full flex">
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
                <div className="flex-1 flex flex-col">
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
                  <div className="flex-1 overflow-auto">
                    <div className="flex h-full">
                      {/* Line Numbers */}
                      <div className="py-4 px-3 select-none bg-[#0A0A0F] text-gray-600 border-r border-white/10">
                        <pre className="text-xs font-mono leading-relaxed text-right">
                          {(selectedFile?.content || previewCode).split('\n').map((_, idx) => (
                            <div key={idx}>{idx + 1}</div>
                          ))}
                        </pre>
                      </div>
                      
                      {/* Code Content */}
                      <div className="flex-1 py-4 px-4 overflow-x-auto bg-[#0A0A0F]">
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
    </div>
  );
}

export default App;
