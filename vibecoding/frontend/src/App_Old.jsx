import React, { useState } from 'react';
import axios from 'axios';
import Header from './components/Header';
import CodePreview from './components/CodePreview';
import ChatPanel from './components/ChatPanel';
import GitPanel from './components/GitPanel';
import { useLocalStorage, useDarkMode, useChatMessages, useCodeVersions } from './hooks/useLocalStorage';
import { downloadCode, copyToClipboard, getSuggestions } from './utils/helpers';
import { applyAllFixes } from './utils/codeFixers';

function App() {
  // Custom hooks for state management
  const [darkMode, toggleDarkMode] = useDarkMode();
  const [messages, addMessage, clearMessages] = useChatMessages();
  const [codeVersions, selectedVersion, addVersion, loadVersion, clearVersions] = useCodeVersions();
  
  // Local state
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [previewCode, setPreviewCode] = useLocalStorage('previewCode', '');
  const [containerPreviewUrl, setContainerPreviewUrl] = useLocalStorage('containerPreviewUrl', '');
  const [activeTab, setActiveTab] = useLocalStorage('activeTab', 'preview');
  const [copied, setCopied] = useState(false);
  const [showGitPanel, setShowGitPanel] = useState(false);
  const [currentProjectId, setCurrentProjectId] = useState('default-project');

  const suggestions = getSuggestions();

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = { 
      role: 'user', 
      content: input,
      timestamp: new Date().toISOString()
    };
    addMessage(userMessage);
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
        timestamp: new Date().toISOString()
      };

      addMessage(aiMessage);
      
      // ALWAYS set code if available
      if (response.data.code) {
        const generatedCode = response.data.code;
        setPreviewCode(generatedCode);
        
        // Save version
        const version = {
          id: Date.now(),
          code: generatedCode,
          prompt: currentInput,
          timestamp: new Date().toISOString(),
          preview_url: response.data.preview_url || null
        };
        addVersion(version);
        
        // Determine preview type
        const isBackendCode = generatedCode.includes('from flask') || 
                             generatedCode.includes('Flask(') ||
                             generatedCode.includes('from django') ||
                             generatedCode.includes('from fastapi') ||
                             generatedCode.includes('import express') ||
                             generatedCode.includes('require(');
        
        if (response.data.preview_url) {
          // Backend app with container
          console.log('🌐 Container preview:', response.data.preview_url);
          setContainerPreviewUrl(response.data.preview_url);
          setActiveTab('preview');
        } else if (isBackendCode) {
          // Backend code without container - show code tab
          console.log('📝 Backend code without container');
          setContainerPreviewUrl('');
          setActiveTab('code');
        } else {
          // Frontend code - use iframe preview
          console.log('🎨 Frontend code - iframe preview');
          setContainerPreviewUrl('');
          setActiveTab('preview');
        }
      }
    } catch (error) {
      console.error('Error:', error);
      addMessage({
        role: 'assistant',
        content: 'Sorry, there was an error processing your request. Please try again.',
        timestamp: new Date().toISOString()
      });
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

  const handleCopyCode = async () => {
    const success = await copyToClipboard(previewCode);
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownloadCode = () => {
    downloadCode(previewCode);
  };

  const handleRefreshPreview = () => {
    // Refresh is now handled internally by CodePreview component
    // This is just a placeholder for compatibility
    console.log('Refresh triggered');
  };

  const handleCopyMessage = async (content) => {
    await copyToClipboard(content);
  };

  const handleRegenerate = (message) => {
    setInput(message.content);
    handleSend();
  };

  const handleClearHistory = () => {
    if (window.confirm('Are you sure you want to clear all chat history?')) {
      clearMessages();
      setPreviewCode('');
      clearVersions();
      localStorage.removeItem('previewCode');
    }
  };

  const handleLoadVersion = (versionId) => {
    const version = loadVersion(versionId);
    if (version) {
      // Apply fixes to old code versions
      const fixedCode = applyAllFixes(version.code);
      setPreviewCode(fixedCode);
      
      // Restore preview URL if available
      if (version.preview_url) {
        setContainerPreviewUrl(version.preview_url);
        setActiveTab('preview');
      } else {
        // Determine if backend or frontend code
        const isBackendCode = fixedCode && (
          fixedCode.includes('from flask') || 
          fixedCode.includes('Flask(') ||
          fixedCode.includes('from django') ||
          fixedCode.includes('from fastapi') ||
          fixedCode.includes('import express') ||
          fixedCode.includes('require(')
        );
        
        setContainerPreviewUrl('');
        setActiveTab(isBackendCode ? 'code' : 'preview');
      }
    }
  };

  const handlePublish = () => {
    // TODO: Implement publish functionality
    console.log('Publish functionality not implemented yet');
  };

  const handleGitClick = () => {
    setShowGitPanel(true);
  };

  const handleCloseGitPanel = () => {
    setShowGitPanel(false);
  };

  return (
    <div className={`h-screen flex flex-col transition-colors duration-300 ${
      darkMode ? 'bg-[#1e1e1e]' : 'bg-[#fafafa]'
    }`}>
      {/* Header */}
      <Header 
        darkMode={darkMode}
        onToggleTheme={toggleDarkMode}
        onPublish={handlePublish}
        onGitClick={handleGitClick}
      />

      {/* Main Content Container */}
      <div className="flex-1 flex overflow-hidden">
        {/* Main Content Area - Left Side */}
        <CodePreview
          previewCode={previewCode}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          darkMode={darkMode}
          copied={copied}
          onCopyCode={handleCopyCode}
          onRefreshPreview={handleRefreshPreview}
          onDownloadCode={handleDownloadCode}
          codeVersions={codeVersions}
          selectedVersion={selectedVersion}
          onLoadVersion={handleLoadVersion}
          containerPreviewUrl={containerPreviewUrl}
        />

        {/* Right Sidebar - Chat Panel */}
        <ChatPanel
          messages={messages}
          loading={loading}
          input={input}
          setInput={setInput}
          onSend={handleSend}
          onKeyPress={handleKeyPress}
          darkMode={darkMode}
          codeVersions={codeVersions}
          selectedVersion={selectedVersion}
          onLoadVersion={handleLoadVersion}
          onCopyMessage={handleCopyMessage}
          onRegenerate={handleRegenerate}
          onClearHistory={handleClearHistory}
          suggestions={suggestions}
        />
      </div>

      {/* Git Panel */}
      <GitPanel
        isVisible={showGitPanel}
        onClose={handleCloseGitPanel}
        darkMode={darkMode}
        projectId={currentProjectId}
      />
    </div>
  );
}

export default App;
