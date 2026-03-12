import { useState } from 'react';
import axios from 'axios';
import { Send, Sparkles, Code, Eye, Download, Copy, Check, Zap, RefreshCw, File, Folder, ChevronRight, ChevronDown } from 'lucide-react';

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [previewCode, setPreviewCode] = useState('');
  const [previewUrl, setPreviewUrl] = useState('');
  const [activeView, setActiveView] = useState('preview'); // preview or code
  const [copied, setCopied] = useState(false);
  const [iframeKey, setIframeKey] = useState(0);
  const [currentProjectId] = useState('default-project');
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileTree, setFileTree] = useState([]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = { role: 'user', content: input };
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
      };

      setMessages(prev => [...prev, aiMessage]);
      
      if (response.data.code) {
        setPreviewCode(response.data.code);
        setIframeKey(prev => prev + 1); // Force iframe refresh
        
        // Parse code to build file tree
        const code = response.data.code;
        const files = parseCodeToFiles(code);
        setFileTree(files);
        if (files.length > 0) {
          setSelectedFile(files[0]);
        }
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
        content: 'Sorry, there was an error. Please try again.'
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

  // Parse code to extract files
  const parseCodeToFiles = (code) => {
    // Check if code contains file markers
    const fileMarkers = code.match(/\/\/\s*FILE:\s*(.+)|#\s*FILE:\s*(.+)|<!--\s*FILE:\s*(.+)\s*-->/gi);
    
    if (fileMarkers && fileMarkers.length > 0) {
      // Multi-file structure
      const files = [];
      const parts = code.split(/\/\/\s*FILE:\s*|#\s*FILE:\s*|<!--\s*FILE:\s*|\s*-->/gi);
      
      for (let i = 1; i < parts.length; i += 2) {
        const filename = parts[i].trim();
        const content = parts[i + 1] || '';
        files.push({
          name: filename,
          path: filename,
          content: content.trim(),
          type: 'file'
        });
      }
      
      return files;
    } else {
      // Single file - detect type
      let filename = 'app.py';
      if (code.includes('from flask') || code.includes('Flask(')) {
        filename = 'app.py';
      } else if (code.includes('from django')) {
        filename = 'app.py';
      } else if (code.includes('from fastapi')) {
        filename = 'app.py';
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
        type: 'file'
      }];
    }
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
          <span className="text-sm text-gray-400">Untitled Project</span>
        </div>
        <div className="flex items-center gap-2">
          <button className="px-4 py-1.5 rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-sm font-medium transition-all">
            Deploy
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel - Chat */}
        <div className="w-96 border-r border-white/10 flex flex-col bg-[#0F0F14]">
          {/* Chat Header */}
          <div className="h-12 border-b border-white/10 flex items-center px-4">
            <Sparkles className="w-4 h-4 mr-2 text-purple-400" />
            <span className="font-medium text-sm">AI Assistant</span>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && (
              <div className="text-center py-12">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 flex items-center justify-center mx-auto mb-4">
                  <Sparkles className="w-8 h-8 text-purple-400" />
                </div>
                <h3 className="text-lg font-semibold mb-2">Start Building</h3>
                <p className="text-sm text-gray-400">Describe what you want to create</p>
                <div className="mt-6 space-y-2">
                  <button
                    onClick={() => setInput('Create a beautiful landing page with gradient background')}
                    className="w-full text-left px-4 py-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors text-sm"
                  >
                    <div className="font-medium mb-1">Landing Page</div>
                    <div className="text-gray-400 text-xs">Beautiful gradient design</div>
                  </button>
                  <button
                    onClick={() => setInput('Build a todo app with Flask backend')}
                    className="w-full text-left px-4 py-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors text-sm"
                  >
                    <div className="font-medium mb-1">Todo App</div>
                    <div className="text-gray-400 text-xs">Flask + SQLite backend</div>
                  </button>
                  <button
                    onClick={() => setInput('Create a calculator app')}
                    className="w-full text-left px-4 py-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors text-sm"
                  >
                    <div className="font-medium mb-1">Calculator</div>
                    <div className="text-gray-400 text-xs">Interactive calculator</div>
                  </button>
                </div>
              </div>
            )}
            
            {messages.map((msg, idx) => (
              <div key={idx} className={`${msg.role === 'user' ? 'text-right' : ''}`}>
                <div className={`inline-block max-w-[85%] rounded-2xl px-4 py-2.5 ${
                  msg.role === 'user'
                    ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white'
                    : 'bg-white/5 text-gray-200'
                }`}>
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ))}
            
            {loading && (
              <div className="flex items-center gap-2 text-gray-400">
                <div className="flex gap-1">
                  <div className="w-2 h-2 rounded-full bg-purple-500 animate-bounce" style={{animationDelay: '0ms'}} />
                  <div className="w-2 h-2 rounded-full bg-purple-500 animate-bounce" style={{animationDelay: '150ms'}} />
                  <div className="w-2 h-2 rounded-full bg-purple-500 animate-bounce" style={{animationDelay: '300ms'}} />
                </div>
                <span className="text-sm">Generating...</span>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="p-4 border-t border-white/10">
            <div className="relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder="Describe your app..."
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 pr-12 text-sm resize-none focus:outline-none focus:border-purple-500/50 transition-colors"
                rows="3"
              />
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className="absolute bottom-3 right-3 w-8 h-8 rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center transition-all"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Right Panel - Preview/Code */}
        <div className="flex-1 flex flex-col">
          {/* View Tabs */}
          <div className="h-12 border-b border-white/10 flex items-center justify-between px-4 bg-[#0F0F14]">
            <div className="flex items-center gap-1">
              <button
                onClick={() => setActiveView('preview')}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  activeView === 'preview'
                    ? 'bg-white/10 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <Eye className="w-4 h-4 inline mr-2" />
                Preview
              </button>
              <button
                onClick={() => setActiveView('code')}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  activeView === 'code'
                    ? 'bg-white/10 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <Code className="w-4 h-4 inline mr-2" />
                Code
              </button>
            </div>
            
            {previewCode && (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleRefresh}
                  className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-sm transition-colors flex items-center gap-2"
                  title="Refresh Preview"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
                <button
                  onClick={handleCopy}
                  className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-sm transition-colors flex items-center gap-2"
                >
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
                <button 
                  onClick={handleDownload}
                  className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-sm transition-colors flex items-center gap-2"
                >
                  <Download className="w-4 h-4" />
                  Download
                </button>
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
                    <button 
                      onClick={handleRefresh}
                      className="p-1.5 rounded hover:bg-white/10"
                      title="Refresh"
                    >
                      <RefreshCw className="w-4 h-4 text-gray-400" />
                    </button>
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
                        <button
                          onClick={() => window.open(previewUrl, '_blank')}
                          className="text-xs px-2 py-0.5 rounded bg-blue-600 text-white hover:bg-blue-700"
                        >
                          Open
                        </button>
                      )}
                    </div>
                  </div>
                </div>
                
                {/* Preview iframe */}
                <div className="flex-1 relative">
                  <iframe
                    key={iframeKey}
                    src={previewUrl || `data:text/html;charset=utf-8,${encodeURIComponent(previewCode)}`}
                    className="w-full h-full border-0"
                    title="Preview"
                    sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                  />
                </div>
              </div>
            ) : (
              <div className="h-full flex">
                {/* File Tree Sidebar */}
                <div className="w-64 border-r border-white/10 bg-[#0F0F14] overflow-y-auto">
                  <div className="p-3 border-b border-white/10">
                    <div className="flex items-center gap-2 text-xs font-semibold text-gray-400 uppercase tracking-wide">
                      <Folder className="w-4 h-4" />
                      <span>Files</span>
                    </div>
                  </div>
                  <div className="p-2">
                    {fileTree.map((file, idx) => (
                      <div
                        key={idx}
                        onClick={() => setSelectedFile(file)}
                        className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors ${
                          selectedFile?.path === file.path
                            ? 'bg-white/10 text-white'
                            : 'text-gray-400 hover:bg-white/5 hover:text-white'
                        }`}
                      >
                        <File className="w-4 h-4 flex-shrink-0" />
                        <span className="truncate">{file.name}</span>
                      </div>
                    ))}
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
      </div>
    </div>
  );
}

export default App;
