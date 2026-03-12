import React, { useState } from 'react';
import axios from 'axios';
import Header from './components/Header';
import CodePreview from './components/CodePreview';
import ChatPanel from './components/ChatPanel';
import { useLocalStorage, useDarkMode, useChatMessages, useCodeVersions } from './hooks/useLocalStorage';
import { downloadCode, copyToClipboard, getSuggestions } from './utils/helpers';

function App() {
  // Custom hooks for state management
  const [darkMode, toggleDarkMode] = useDarkMode();
  const [messages, addMessage, clearMessages] = useChatMessages();
  const [codeVersions, selectedVersion, addVersion, loadVersion, clearVersions] = useCodeVersions();
  
  // Local state
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [previewCode, setPreviewCode] = useLocalStorage('previewCode', '');
  const [activeTab, setActiveTab] = useLocalStorage('activeTab', 'preview');
  const [copied, setCopied] = useState(false);

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
      const response = await axios.post('/api/generate', {
        prompt: currentInput,
        history: messages
      });

      const aiMessage = {
        role: 'assistant',
        content: response.data.message,
        code: response.data.code,
        timestamp: new Date().toISOString()
      };

      addMessage(aiMessage);
      
      if (response.data.code) {
        setPreviewCode(response.data.code);
        setActiveTab('preview');
        
        // Save code version
        const version = {
          id: Date.now(),
          code: response.data.code,
          prompt: currentInput,
          timestamp: new Date().toISOString()
        };
        addVersion(version);
      }
    } catch (error) {
      console.error('Error:', error);
      addMessage({
        role: 'assistant',
        content: 'Sorry, there was an error processing your request. Please try again.'
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
    // Force iframe refresh by updating the srcDoc
    const temp = previewCode;
    setPreviewCode('');
    setTimeout(() => setPreviewCode(temp), 100);
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
      setPreviewCode(version.code);
      setActiveTab('preview');
    }
  };

  const handlePublish = () => {
    // TODO: Implement publish functionality
    console.log('Publish functionality not implemented yet');
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
    </div>
  );
}

export default App;
