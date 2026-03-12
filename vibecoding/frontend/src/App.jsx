import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, Code, Eye, Download, RefreshCw, Moon, Sun, Zap, Terminal, Layers, Copy, Check, Plus, MoreHorizontal, User, Bot, CheckCircle2 } from 'lucide-react';
import axios from 'axios';

function App() {
  // Load persisted state from localStorage
  const [messages, setMessages] = useState(() => {
    try {
      const saved = localStorage.getItem('chatMessages');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  
  const [previewCode, setPreviewCode] = useState(() => {
    try {
      return localStorage.getItem('previewCode') || '';
    } catch {
      return '';
    }
  });
  
  const [activeTab, setActiveTab] = useState(() => {
    try {
      return localStorage.getItem('activeTab') || 'preview';
    } catch {
      return 'preview';
    }
  });
  
  const [darkMode, setDarkMode] = useState(() => {
    try {
      const saved = localStorage.getItem('darkMode');
      return saved ? JSON.parse(saved) : true;
    } catch {
      return true;
    }
  });
  
  const [copied, setCopied] = useState(false);
  const [codeVersions, setCodeVersions] = useState(() => {
    try {
      const saved = localStorage.getItem('codeVersions');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [selectedVersion, setSelectedVersion] = useState(null);
  const messagesEndRef = useRef(null);
  const iframeRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Persist codeVersions to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('codeVersions', JSON.stringify(codeVersions));
    } catch (err) {
      console.error('Failed to save code versions:', err);
    }
  }, [codeVersions]);

  // Persist messages to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('chatMessages', JSON.stringify(messages));
    } catch (err) {
      console.error('Failed to save messages:', err);
    }
  }, [messages]);

  // Persist previewCode to localStorage
  useEffect(() => {
    try {
      if (previewCode) {
        localStorage.setItem('previewCode', previewCode);
      }
    } catch (err) {
      console.error('Failed to save preview code:', err);
    }
  }, [previewCode]);

  // Persist activeTab to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('activeTab', activeTab);
    } catch (err) {
      console.error('Failed to save active tab:', err);
    }
  }, [activeTab]);

  // Persist darkMode to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('darkMode', JSON.stringify(darkMode));
    } catch (err) {
      console.error('Failed to save dark mode:', err);
    }
  }, [darkMode]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (previewCode && iframeRef.current) {
      const iframe = iframeRef.current;
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      doc.open();
      doc.write(previewCode);
      doc.close();
    }
  }, [previewCode]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = { 
      role: 'user', 
      content: input,
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await axios.post('/api/generate', {
        prompt: input,
        history: messages
      });

      const aiMessage = {
        role: 'assistant',
        content: response.data.message,
        code: response.data.code,
        timestamp: new Date().toISOString()
      };

      setMessages(prev => [...prev, aiMessage]);
      
      if (response.data.code) {
        setPreviewCode(response.data.code);
        setActiveTab('preview');
        
        // Save code version
        const version = {
          id: Date.now(),
          code: response.data.code,
          prompt: input,
          timestamp: new Date().toISOString()
        };
        setCodeVersions(prev => [...prev, version]);
        setSelectedVersion(version.id);
      }
    } catch (error) {
      console.error('Error:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, there was an error processing your request. Please try again.'
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const downloadCode = () => {
    const blob = new Blob([previewCode], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'app.html';
    a.click();
    URL.revokeObjectURL(url);
  };

  const refreshPreview = () => {
    if (iframeRef.current) {
      iframeRef.current.src = iframeRef.current.src;
    }
  };

  const copyCode = () => {
    navigator.clipboard.writeText(previewCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const toggleTheme = () => {
    setDarkMode(!darkMode);
  };

  const clearHistory = () => {
    if (window.confirm('Are you sure you want to clear all chat history?')) {
      setMessages([]);
      setPreviewCode('');
      setCodeVersions([]);
      setSelectedVersion(null);
      localStorage.removeItem('chatMessages');
      localStorage.removeItem('previewCode');
      localStorage.removeItem('codeVersions');
    }
  };

  const loadVersion = (versionId) => {
    const version = codeVersions.find(v => v.id === versionId);
    if (version) {
      setPreviewCode(version.code);
      setSelectedVersion(versionId);
      setActiveTab('preview');
    }
  };

  // Format code with proper indentation and syntax highlighting
  const formatCode = (code) => {
    if (!code) return '';
    
    try {
      // Basic HTML formatting
      let formatted = code;
      let indent = 0;
      const lines = formatted.split('\n');
      const formattedLines = lines.map(line => {
        const trimmed = line.trim();
        
        // Decrease indent for closing tags
        if (trimmed.startsWith('</') || trimmed.startsWith('}') || trimmed.startsWith(']')) {
          indent = Math.max(0, indent - 1);
        }
        
        const indentedLine = '  '.repeat(indent) + trimmed;
        
        // Increase indent for opening tags
        if (trimmed.startsWith('<') && !trimmed.startsWith('</') && !trimmed.endsWith('/>') && !trimmed.includes('</')) {
          indent++;
        } else if (trimmed.endsWith('{') || trimmed.endsWith('[')) {
          indent++;
        }
        
        return indentedLine;
      });
      
      return formattedLines.join('\n');
    } catch {
      return code;
    }
  };

  return (
    <div className={`h-screen flex flex-col transition-colors duration-300 ${
      darkMode ? 'bg-[#1e1e1e]' : 'bg-[#fafafa]'
    }`}>
      {/* Top Navbar */}
      <div className={`flex items-center justify-between px-6 py-3 border-b ${
        darkMode ? 'bg-[#252526] border-[#3e3e42]' : 'bg-white border-gray-200'
      }`}>
        <div className="flex items-center gap-3">
          <img src="/logo.png" alt="Bourtec" className="h-8 w-auto" />
          <span className={`text-base font-semibold ${
            darkMode ? 'text-[#cccccc]' : 'text-gray-900'
          }`}>VibeCoding</span>
        </div>
        
        <div className="flex items-center gap-3">
          <button
            onClick={toggleTheme}
            className={`p-2 rounded-lg transition-colors ${
              darkMode 
                ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
                : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
            }`}
          >
            {darkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
          <button className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            darkMode 
              ? 'bg-[#0e639c] text-white hover:bg-[#1177bb]' 
              : 'bg-gray-900 text-white hover:bg-gray-800'
          }`}>
            Publish
          </button>
        </div>
      </div>

      {/* Main Content Container */}
      <div className="flex-1 flex overflow-hidden">
        {/* Main Content Area - Left Side */}
        <div className="flex-1 flex flex-col">
          {/* Tab Bar */}
          <div className={`flex items-center gap-2 px-6 py-2 border-b ${
            darkMode ? 'bg-[#252526] border-[#3e3e42]' : 'bg-gray-50 border-gray-200'
          }`}>
            <button
              onClick={() => setActiveTab('preview')}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                activeTab === 'preview'
                  ? darkMode
                    ? 'bg-[#1e1e1e] text-white border border-[#3e3e42]'
                    : 'bg-white text-gray-900 border border-gray-300 shadow-sm'
                  : darkMode
                    ? 'text-[#cccccc] hover:text-white hover:bg-[#2d2d30]'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
              }`}
            >
              <div className="flex items-center gap-2">
                <Eye className="w-4 h-4" />
                Preview
              </div>
            </button>
            <button
              onClick={() => setActiveTab('code')}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                activeTab === 'code'
                  ? darkMode
                    ? 'bg-[#1e1e1e] text-white border border-[#3e3e42]'
                    : 'bg-white text-gray-900 border border-gray-300 shadow-sm'
                  : darkMode
                    ? 'text-[#cccccc] hover:text-white hover:bg-[#2d2d30]'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
              }`}
            >
              <div className="flex items-center gap-2">
                <Code className="w-4 h-4" />
                Code
              </div>
            </button>
            
            {previewCode && (
              <div className="ml-auto flex items-center gap-2">
                {/* Version Selector */}
                {codeVersions.length > 1 && (
                  <div className="flex items-center gap-2">
                    <span className={`text-xs ${
                      darkMode ? 'text-[#858585]' : 'text-gray-500'
                    }`}>Version:</span>
                    <select
                      value={selectedVersion || ''}
                      onChange={(e) => loadVersion(Number(e.target.value))}
                      className={`px-2 py-1 rounded-md text-xs transition-colors ${
                        darkMode 
                          ? 'bg-[#2d2d30] text-[#cccccc] border border-[#3e3e42] hover:bg-[#3e3e42]' 
                          : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
                      }`}
                    >
                      {codeVersions.map((version, idx) => (
                        <option key={version.id} value={version.id}>
                          v{codeVersions.length - idx} - {new Date(version.timestamp).toLocaleTimeString()}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                
                <button
                  onClick={copyCode}
                  className={`p-2 rounded-md transition-colors ${
                    darkMode 
                      ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
                      : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
                  }`}
                  title="Copy Code"
                >
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </button>
                <button
                  onClick={refreshPreview}
                  className={`p-2 rounded-md transition-colors ${
                    darkMode 
                      ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
                      : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
                  }`}
                  title="Refresh"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
                <button
                  onClick={downloadCode}
                  className={`p-2 rounded-md transition-colors ${
                    darkMode 
                      ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
                      : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
                  }`}
                  title="Download"
                >
                  <Download className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>

          {/* Preview/Code Area */}
          <div className={`flex-1 ${
            darkMode ? 'bg-[#1e1e1e]' : 'bg-white'
          }`}>
            {!previewCode ? (
              <div className="h-full flex items-center justify-center">
                <div className="text-center">
                  <div className={`w-20 h-20 rounded-2xl mx-auto mb-4 flex items-center justify-center ${
                    darkMode ? 'bg-[#2d2d30]' : 'bg-gray-100'
                  }`}>
                    <Sparkles className={`w-10 h-10 ${darkMode ? 'text-[#858585]' : 'text-gray-400'}`} />
                  </div>
                  <h3 className={`text-base font-medium mb-2 ${
                    darkMode ? 'text-[#cccccc]' : 'text-gray-600'
                  }`}>
                    Start building your idea
                  </h3>
                  <p className={`text-sm ${darkMode ? 'text-[#858585]' : 'text-gray-400'}`}>
                    Describe what you want in the chat panel
                  </p>
                </div>
              </div>
            ) : activeTab === 'preview' ? (
              <iframe
                ref={iframeRef}
                className="w-full h-full"
                title="Preview"
                sandbox="allow-scripts allow-same-origin"
              />
            ) : (
              <div className={`h-full overflow-auto custom-scrollbar ${
                darkMode ? 'bg-[#1e1e1e]' : 'bg-gray-50'
              }`}>
                <div className="p-6">
                  {/* Code Header */}
                  <div className={`flex items-center justify-between mb-4 pb-3 border-b ${
                    darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
                  }`}>
                    <div className="flex items-center gap-2">
                      <Code className={`w-4 h-4 ${darkMode ? 'text-[#858585]' : 'text-gray-500'}`} />
                      <span className={`text-sm font-medium ${
                        darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                      }`}>Generated Code</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs ${
                        darkMode ? 'text-[#858585]' : 'text-gray-500'
                      }`}>{previewCode.split('\n').length} lines</span>
                      <button
                        onClick={copyCode}
                        className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                          darkMode 
                            ? 'bg-[#2d2d30] text-[#cccccc] hover:bg-[#3e3e42]' 
                            : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                        }`}
                      >
                        {copied ? (
                          <span className="flex items-center gap-1">
                            <Check className="w-3 h-3" />
                            Copied
                          </span>
                        ) : (
                          <span className="flex items-center gap-1">
                            <Copy className="w-3 h-3" />
                            Copy
                          </span>
                        )}
                      </button>
                    </div>
                  </div>
                  
                  {/* Code Content with Line Numbers */}
                  <div className={`rounded-lg overflow-hidden border ${
                    darkMode ? 'bg-[#1e1e1e] border-[#3e3e42]' : 'bg-white border-gray-200'
                  }`}>
                    <div className="flex">
                      {/* Line Numbers */}
                      <div className={`py-4 px-3 select-none ${
                        darkMode ? 'bg-[#252526] text-[#858585]' : 'bg-gray-50 text-gray-400'
                      }`}>
                        <pre className="text-xs font-mono leading-relaxed text-right">
                          {formatCode(previewCode).split('\n').map((_, idx) => (
                            <div key={idx}>{idx + 1}</div>
                          ))}
                        </pre>
                      </div>
                      
                      {/* Code Content */}
                      <div className="flex-1 py-4 px-4 overflow-x-auto">
                        <pre className={`text-sm font-mono leading-relaxed ${
                          darkMode ? 'text-[#d4d4d4]' : 'text-gray-800'
                        }`}>
                          <code className="language-html">{formatCode(previewCode)}</code>
                        </pre>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Sidebar - Chat Panel */}
        <div className={`w-[380px] flex flex-col border-l ${
          darkMode ? 'bg-[#252526] border-[#3e3e42]' : 'bg-white border-gray-200'
        }`}>
          {/* Chat Header */}
          <div className={`flex items-center justify-between px-4 py-3 border-b ${
            darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
          }`}>
            <div className="flex items-center gap-2">
              <div className={`p-2 rounded-lg ${
                darkMode ? 'bg-[#0e639c]' : 'bg-blue-500'
              }`}>
                <Sparkles className="w-4 h-4 text-white" />
              </div>
              <div>
                <span className={`text-sm font-semibold block ${
                  darkMode ? 'text-[#cccccc]' : 'text-gray-900'
                }`}>AI Assistant</span>
                <span className={`text-xs ${
                  darkMode ? 'text-[#858585]' : 'text-gray-500'
                }`}>{messages.length} messages</span>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {messages.length > 0 && (
                <button 
                  onClick={clearHistory}
                  className={`p-2 rounded-lg transition-colors ${
                    darkMode 
                      ? 'hover:bg-[#2d2d30] text-[#858585] hover:text-[#cccccc]' 
                      : 'hover:bg-gray-100 text-gray-500 hover:text-gray-700'
                  }`}
                  title="Clear history"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              )}
              <button className={`p-2 rounded-lg transition-colors ${
                darkMode 
                  ? 'hover:bg-[#2d2d30] text-[#cccccc]' 
                  : 'hover:bg-gray-100 text-gray-600'
              }`}>
                <MoreHorizontal className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Suggestions Section */}
          {messages.length === 0 && (
            <div className={`px-4 py-3 border-b ${
              darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
            }`}>
              <div className="flex items-center gap-2 mb-3">
                <Zap className={`w-4 h-4 ${darkMode ? 'text-[#858585]' : 'text-gray-500'}`} />
                <span className={`text-xs font-medium ${
                  darkMode ? 'text-[#858585]' : 'text-gray-500'
                }`}>Suggestions</span>
              </div>
              <div className="space-y-2">
                <button
                  onClick={() => setInput("Add Dynamic Blog Section")}
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all ${
                    darkMode 
                      ? 'bg-[#2d2d30] hover:bg-[#3e3e42] text-[#cccccc] border border-[#3e3e42]' 
                      : 'bg-gray-50 hover:bg-gray-100 text-gray-700 border border-gray-200'
                  }`}
                >
                  Add Dynamic Blog Section
                </button>
                <button
                  onClick={() => setInput("Add Responsive Contact Form")}
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all ${
                    darkMode 
                      ? 'bg-[#2d2d30] hover:bg-[#3e3e42] text-[#cccccc] border border-[#3e3e42]' 
                      : 'bg-gray-50 hover:bg-gray-100 text-gray-700 border border-gray-200'
                  }`}
                >
                  Add Responsive Contact Form
                </button>
                <button
                  onClick={() => setInput("Implement Theme Toggle")}
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all ${
                    darkMode 
                      ? 'bg-[#2d2d30] hover:bg-[#3e3e42] text-[#cccccc] border border-[#3e3e42]' 
                      : 'bg-gray-50 hover:bg-gray-100 text-gray-700 border border-gray-200'
                  }`}
                >
                  Implement Theme Toggle
                </button>
              </div>
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 custom-scrollbar">
            {messages.map((msg, idx) => {
              const msgVersion = msg.code ? codeVersions.find(v => 
                Math.abs(new Date(v.timestamp).getTime() - new Date(msg.timestamp).getTime()) < 1000
              ) : null;
              
              return (
                <div key={idx} className="message-item">
                  <div className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                    <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${
                      msg.role === 'user'
                        ? darkMode ? 'bg-[#0e639c]' : 'bg-blue-500'
                        : darkMode ? 'bg-[#2d2d30]' : 'bg-gray-100'
                    }`}>
                      {msg.role === 'user' ? (
                        <User className="w-4 h-4 text-white" />
                      ) : (
                        <Bot className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} />
                      )}
                    </div>
                    <div className="flex-1">
                      <div className={`${
                        msg.role === 'user'
                          ? darkMode
                            ? 'bg-[#0e639c] text-white'
                            : 'bg-blue-500 text-white'
                          : darkMode
                            ? 'bg-[#2d2d30] text-[#cccccc]'
                            : 'bg-gray-100 text-gray-900'
                      } rounded-lg px-4 py-3`}>
                        <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                        {msg.code && (
                          <div className={`mt-3 pt-3 border-t flex items-center justify-between ${
                            msg.role === 'user'
                              ? 'border-white/20'
                              : darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
                          }`}>
                            <div className={`flex items-center gap-2 text-xs ${
                              msg.role === 'user'
                                ? 'text-white/80'
                                : darkMode ? 'text-[#858585]' : 'text-gray-500'
                            }`}>
                              <CheckCircle2 className="w-3.5 h-3.5" />
                              <span>Code generated</span>
                            </div>
                            {msgVersion && (
                              <button
                                onClick={() => loadVersion(msgVersion.id)}
                                className={`text-xs px-2 py-1 rounded transition-colors ${
                                  selectedVersion === msgVersion.id
                                    ? darkMode
                                      ? 'bg-[#0e639c] text-white'
                                      : 'bg-blue-500 text-white'
                                    : msg.role === 'user'
                                      ? 'text-white/80 hover:bg-white/10'
                                      : darkMode
                                        ? 'text-[#858585] hover:bg-[#3e3e42]'
                                        : 'text-gray-500 hover:bg-gray-200'
                                }`}
                              >
                                {selectedVersion === msgVersion.id ? 'Current' : 'View'}
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                      {msg.timestamp && (
                        <div className={`text-xs mt-1 ${
                          msg.role === 'user' ? 'text-right' : 'text-left'
                        } ${darkMode ? 'text-[#858585]' : 'text-gray-400'}`}>
                          {new Date(msg.timestamp).toLocaleTimeString()}
                        </div>
                      )}
                    </div>
                  </div>
                  {msg.role === 'assistant' && (
                    <div className="flex items-center gap-2 mt-2 ml-11">
                      <button className={`text-xs px-2 py-1 rounded-md transition-colors ${
                        darkMode 
                          ? 'text-[#858585] hover:text-[#cccccc] hover:bg-[#2d2d30]' 
                          : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                      }`}>
                        <Copy className="w-3 h-3 inline mr-1" />
                        Copy
                      </button>
                      <button className={`text-xs px-2 py-1 rounded-md transition-colors ${
                        darkMode 
                          ? 'text-[#858585] hover:text-[#cccccc] hover:bg-[#2d2d30]' 
                          : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                      }`}>
                        <RefreshCw className="w-3 h-3 inline mr-1" />
                        Regenerate
                      </button>
                    </div>
                  )}
                </div>
              );
            })}

            {loading && (
              <div className="flex gap-3">
                <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${
                  darkMode ? 'bg-[#2d2d30]' : 'bg-gray-100'
                }`}>
                  <Bot className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} />
                </div>
                <div className={`px-4 py-3 rounded-lg ${
                  darkMode ? 'bg-[#2d2d30]' : 'bg-gray-100'
                }`}>
                  <div className="flex gap-1.5">
                    <span className={`w-2 h-2 rounded-full animate-bounce ${
                      darkMode ? 'bg-[#858585]' : 'bg-gray-400'
                    }`} style={{ animationDelay: '0ms' }}></span>
                    <span className={`w-2 h-2 rounded-full animate-bounce ${
                      darkMode ? 'bg-[#858585]' : 'bg-gray-400'
                    }`} style={{ animationDelay: '150ms' }}></span>
                    <span className={`w-2 h-2 rounded-full animate-bounce ${
                      darkMode ? 'bg-[#858585]' : 'bg-gray-400'
                    }`} style={{ animationDelay: '300ms' }}></span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <div className={`p-4 border-t ${
            darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
          }`}>
            <div className="relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="What would you like to change?"
                disabled={loading}
                rows="3"
                className={`w-full px-4 py-3 pr-12 rounded-lg text-sm resize-none transition-colors focus:outline-none focus:ring-2 ${
                  darkMode 
                    ? 'bg-[#2d2d30] text-[#cccccc] placeholder-[#858585] focus:ring-[#0e639c] border border-[#3e3e42]' 
                    : 'bg-gray-50 text-gray-900 placeholder-gray-400 focus:ring-blue-500 border border-gray-200'
                }`}
              />
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className={`absolute right-3 bottom-3 p-2 rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                  darkMode 
                    ? 'bg-[#0e639c] text-white hover:bg-[#1177bb]' 
                    : 'bg-blue-500 text-white hover:bg-blue-600'
                }`}
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
            <div className={`flex items-center justify-between mt-2 text-xs ${
              darkMode ? 'text-[#858585]' : 'text-gray-400'
            }`}>
              <div className="flex items-center gap-3">
                <button className={`flex items-center gap-1 transition-colors ${
                  darkMode ? 'hover:text-[#cccccc]' : 'hover:text-gray-600'
                }`}>
                  <Plus className="w-3.5 h-3.5" />
                  <span>Attach</span>
                </button>
              </div>
              <span>Press Enter to send</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
