import React, { useState, useEffect } from 'react';
import { 
  GitBranch, 
  Plus, 
  GitCommit, 
  GitPullRequest, 
  GitMerge,
  RefreshCw,
  X,
  Check,
  AlertCircle,
  FileText,
  PlusCircle,
  MinusCircle,
  Sparkles,
  Settings,
  Globe,
  Key,
  Upload
} from 'lucide-react';
import { Button } from './ui/button';
import Typewriter from './Typewriter';
import { cn } from '@/lib/utils';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const GitPanel = ({ 
  darkMode, 
  isVisible, 
  onClose, 
  projectId,
  onGitOperation 
}) => {
  const [gitStatus, setGitStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [commitMessage, setCommitMessage] = useState('');
  const [branchName, setBranchName] = useState('');
  const [showCommitInput, setShowCommitInput] = useState(false);
  const [showBranchInput, setShowBranchInput] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState(new Set());
  const [activeTab, setActiveTab] = useState('status');
  const [suggestionIndex, setSuggestionIndex] = useState(0);
  const [remoteUrl, setRemoteUrl] = useState('');
  const [username, setUsername] = useState('');
  const [token, setToken] = useState('');
  const [pushLoading, setPushLoading] = useState(false);
  const [branches, setBranches] = useState([]);
  const [branchLoading, setBranchLoading] = useState(false);

  useEffect(() => {
    // Load git credentials from localStorage
    const savedRemote = localStorage.getItem(`git_remote_${projectId}`);
    const savedUser = localStorage.getItem('git_username');
    const savedToken = localStorage.getItem('git_token');
    
    if (savedRemote) setRemoteUrl(savedRemote);
    if (savedUser) setUsername(savedUser);
    if (savedToken) setToken(savedToken);
  }, [projectId]);

  const gitSuggestions = [
    "Initialize git to share your progress",
    "Track changes with commit points",
    "Branch out to experiment safely",
    "Version control your coding vibes"
  ];

  useEffect(() => {
    if (isVisible && projectId) {
      fetchGitStatus();
      if (activeTab === 'branches') {
        fetchBranches();
      }
    }
  }, [isVisible, projectId, activeTab]);

  const fetchGitStatus = async () => {
    if (!projectId) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/git/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId })
      });
      const data = await response.json();
      setGitStatus(data);
    } catch (error) {
      console.error('Error fetching git status:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleGitInit = async () => {
    if (!projectId) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/git/init`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId })
      });
      const data = await response.json();
      if (data.status === 'success') {
        fetchGitStatus();
      }
    } catch (error) {
      console.error('Error initializing git:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddFiles = async (files = null) => {
    if (!projectId) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/git/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          project_id: projectId,
          files: files ? Array.from(files) : null
        })
      });
      const data = await response.json();
      if (data.status === 'success') {
        fetchGitStatus();
        setSelectedFiles(new Set());
      }
    } catch (error) {
      console.error('Error adding files:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!projectId || !commitMessage.trim()) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/git/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          project_id: projectId,
          message: commitMessage 
        })
      });
      const data = await response.json();
      if (data.status === 'success') {
        setCommitMessage('');
        setShowCommitInput(false);
        fetchGitStatus();
      }
    } catch (error) {
      console.error('Error committing:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchBranches = async () => {
    if (!projectId) return;
    setBranchLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/git/branches`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          project_id: projectId,
          username: username,
          token: token
        })
      });
      const data = await response.json();
      if (data.status === 'success') {
        setBranches(data.branches || []);
      }
    } catch (error) {
      console.error('Error fetching branches:', error);
    } finally {
      setBranchLoading(false);
    }
  };

  const handleCreateBranch = async () => {
    if (!projectId || !branchName.trim()) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/git/branch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          project_id: projectId,
          branch_name: branchName 
        })
      });
      const data = await response.json();
      if (data.status === 'success') {
        setBranchName('');
        setShowBranchInput(false);
        fetchGitStatus();
      }
    } catch (error) {
      console.error('Error creating branch:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveRemote = async () => {
    if (!projectId || !remoteUrl.trim()) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/git/remote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          project_id: projectId,
          remote_url: remoteUrl 
        })
      });
      const data = await response.json();
      if (data.status === 'success') {
        localStorage.setItem(`git_remote_${projectId}`, remoteUrl);
        localStorage.setItem('git_username', username);
        localStorage.setItem('git_token', token);
        
        // Refresh git data for the new repo
        await fetchGitStatus();
        await fetchBranches();
        
        alert('Remote settings saved successfully!');
      } else {
        alert('Failed to save remote: ' + (data.message || 'Unknown error'));
      }
    } catch (error) {
      console.error('Error saving remote:', error);
      alert('Error saving remote. Check console.');
    } finally {
      setLoading(false);
    }
  };

  const handlePush = async () => {
    if (!projectId) return;
    
    setPushLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/git/push`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          project_id: projectId,
          remote_name: 'origin',
          branch_name: gitStatus?.branch || 'main',
          username: username,
          token: token
        })
      });
      const data = await response.json();
      if (data.status === 'success') {
        alert('Push successful!');
      } else {
        alert(`Push failed: ${data.stderr || data.message || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error pushing:', error);
      alert('Error pushing code. Check console.');
    } finally {
      setPushLoading(false);
    }
  };

  const toggleFileSelection = (filename) => {
    const newSelected = new Set(selectedFiles);
    if (newSelected.has(filename)) {
      newSelected.delete(filename);
    } else {
      newSelected.add(filename);
    }
    setSelectedFiles(newSelected);
  };

  if (!isVisible) return null;

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50`}>
      <div className={`w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden rounded-lg shadow-2xl ${
        darkMode ? 'bg-[#252526] border-[#3e3e42]' : 'bg-white border-gray-200'
      } border`}>
        {/* Header */}
        <div className={`flex items-center justify-between px-6 py-4 border-b ${
          darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
        }`}>
          <div className="flex items-center gap-3">
            <GitBranch className="w-5 h-5" />
            <h2 className={`text-lg font-semibold ${
              darkMode ? 'text-[#cccccc]' : 'text-gray-900'
            }`}>Git Integration</h2>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={fetchGitStatus}
              className={`${
                darkMode 
                  ? 'hover:bg-[#2d2d30] text-[#cccccc]' 
                  : 'hover:bg-gray-100 text-gray-600'
              }`}
              disabled={loading}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handlePush}
              disabled={loading || pushLoading || !gitStatus}
              className={`mr-2 flex items-center gap-2 ${
                darkMode ? 'hover:bg-[#2d2d30] text-[#cccccc]' : 'hover:bg-gray-100 text-gray-600'
              }`}
            >
              <Upload className={`w-4 h-4 ${pushLoading ? 'animate-bounce' : ''}`} />
              {pushLoading ? 'Pushing...' : 'Push'}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              className={`${
                darkMode 
                  ? 'hover:bg-[#2d2d30] text-[#cccccc]' 
                  : 'hover:bg-gray-100 text-gray-600'
              }`}
            >
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Content */}
        <div className="flex flex-col flex-1 min-h-0">
          {/* Tabs */}
          <div className={`flex border-b ${
            darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
          }`}>
            {['status', 'commits', 'branches', 'settings'].map((tab) => (
              <Button
                key={tab}
                variant="ghost"
                onClick={() => {
                  setActiveTab(tab);
                  if (tab === 'branches') fetchBranches();
                  if (tab === 'status') fetchGitStatus();
                }}
                className={`rounded-none capitalize ${
                  activeTab === tab
                    ? darkMode 
                      ? 'bg-[#0e639c] text-white' 
                      : 'bg-gray-900 text-white'
                    : darkMode
                      ? 'text-[#cccccc] hover:bg-[#2d2d30]'
                      : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                {tab}
              </Button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-y-auto p-6">
            {loading ? (
              <div className="flex items-center justify-center h-64">
                <RefreshCw className="w-6 h-6 animate-spin" />
              </div>
            ) : (!gitStatus || gitStatus.status === 'not_initialized') ? (
              <div className="text-center py-8">
                <div className={`w-20 h-20 rounded-2xl mx-auto mb-6 flex items-center justify-center ${
                  darkMode ? 'bg-white/5' : 'bg-gray-100'
                }`}>
                  <GitBranch className={`w-10 h-10 ${darkMode ? 'text-blue-400' : 'text-blue-600'}`} />
                </div>
                <h3 className={`text-lg font-medium mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
                  Version Control
                </h3>
                <div className="flex items-center justify-center gap-2 mb-8 h-6">
                  <Sparkles className="w-4 h-4 text-purple-400 opacity-70" />
                  <p className={`text-sm ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                    <Typewriter 
                      key={suggestionIndex}
                      text={gitSuggestions[suggestionIndex]} 
                      delay={40}
                      waitBeforeDelete={2000}
                      onComplete={() => {
                        setSuggestionIndex((prev) => (prev + 1) % gitSuggestions.length);
                      }}
                    />
                  </p>
                </div>
                <Button
                  onClick={handleGitInit}
                  size="lg"
                  className={`${
                    darkMode 
                      ? 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700' 
                      : 'bg-blue-600 hover:bg-blue-700'
                  } text-white shadow-lg shadow-blue-500/20 px-8 rounded-xl font-medium transition-all hover:scale-[1.02] active:scale-[0.98]`}
                >
                  <Plus className="w-4 h-4 mr-2" />
                  Initialize Repository
                  </Button>
                </div>
              ) : (
                <>
                  {activeTab === 'settings' && (
                    <div className="space-y-6">
                      <div className={`p-6 rounded-xl border ${
                        darkMode ? 'bg-[#2d2d30] border-[#3e3e42]' : 'bg-white border-gray-200'
                      }`}>
                        <div className="flex items-center gap-2 mb-6">
                          <Globe className="w-5 h-5 text-blue-500" />
                          <h3 className={`text-lg font-medium ${darkMode ? 'text-white' : 'text-gray-900'}`}>
                            Remote Repository
                          </h3>
                        </div>
                        
                        <div className="space-y-4">
                          <div>
                            <label className={`block text-xs font-medium mb-1.5 uppercase tracking-wider ${
                              darkMode ? 'text-gray-400' : 'text-gray-500'
                            }`}>
                              Repository URL
                            </label>
                            <input
                              type="text"
                              value={remoteUrl}
                              onChange={(e) => setRemoteUrl(e.target.value)}
                              placeholder="https://github.com/username/repo.git"
                              className={`w-full px-4 py-2.5 rounded-lg border transition-all outline-none focus:ring-2 ${
                                darkMode 
                                  ? 'bg-[#1e1e1e] border-[#3e3e42] text-white focus:ring-blue-500/50' 
                                  : 'bg-white border-gray-200 text-gray-900 focus:ring-blue-500/20'
                              }`}
                            />
                          </div>
                          
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label className={`block text-xs font-medium mb-1.5 uppercase tracking-wider ${
                                darkMode ? 'text-gray-400' : 'text-gray-500'
                              }`}>
                                Username (Optional)
                              </label>
                              <input
                                type="text"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                placeholder="git-user"
                                className={`w-full px-4 py-2.5 rounded-lg border transition-all outline-none focus:ring-2 ${
                                  darkMode 
                                    ? 'bg-[#1e1e1e] border-[#3e3e42] text-white focus:ring-blue-500/50' 
                                    : 'bg-white border-gray-200 text-gray-900 focus:ring-blue-500/20'
                                }`}
                              />
                            </div>
                            <div>
                              <label className={`block text-xs font-medium mb-1.5 uppercase tracking-wider ${
                                darkMode ? 'text-gray-400' : 'text-gray-500'
                              }`}>
                                Personal Access Token
                              </label>
                              <div className="relative">
                                <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                                <input
                                  type="password"
                                  value={token}
                                  onChange={(e) => setToken(e.target.value)}
                                  placeholder="ghp_xxxxxxxxxxxx"
                                  className={`w-full pl-10 pr-4 py-2.5 rounded-lg border transition-all outline-none focus:ring-2 ${
                                    darkMode 
                                      ? 'bg-[#1e1e1e] border-[#3e3e42] text-white focus:ring-blue-500/50' 
                                      : 'bg-white border-gray-200 text-gray-900 focus:ring-blue-500/20'
                                  }`}
                                />
                              </div>
                            </div>
                          </div>
                          
                          <div className="pt-2">
                            <Button
                              onClick={handleSaveRemote}
                              disabled={loading || !remoteUrl}
                              className={`w-full ${
                                darkMode ? 'bg-blue-600 hover:bg-blue-700' : 'bg-gray-900 hover:bg-gray-800'
                              } text-white font-medium py-2.5 rounded-lg`}
                            >
                              Save Remote Settings
                            </Button>
                          </div>
                        </div>
                      </div>

                      <div className={`p-4 rounded-lg flex items-start gap-3 ${
                        darkMode ? 'bg-yellow-500/10 border border-yellow-500/20' : 'bg-yellow-50 border border-yellow-100'
                      }`}>
                        <AlertCircle className={`w-5 h-5 shrink-0 ${darkMode ? 'text-yellow-500' : 'text-yellow-600'}`} />
                        <div className="space-y-1">
                          <p className={`text-sm font-medium ${darkMode ? 'text-yellow-400' : 'text-yellow-800'}`}>Security Note</p>
                          <p className={`text-xs ${darkMode ? 'text-yellow-200/70' : 'text-yellow-600'}`}>
                            Your credentials are saved locally in your browser and used only for git operations from this machine. 
                            Always use a Personal Access Token with minimal required permissions.
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                  {activeTab === 'status' && (
                  <div className="space-y-6">
                    {/* Repository Info */}
                    <div className={`p-4 rounded-lg ${
                      darkMode ? 'bg-[#2d2d30]' : 'bg-gray-50'
                    }`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <GitBranch className="w-4 h-4" />
                          <span className={`font-medium ${
                            darkMode ? 'text-[#cccccc]' : 'text-gray-900'
                          }`}>
                            {gitStatus.branch}
                          </span>
                        </div>
                        {gitStatus.has_changes && (
                          <span className={`px-2 py-1 text-xs rounded-full ${
                            darkMode ? 'bg-[#0e639c] text-white' : 'bg-blue-100 text-blue-800'
                          }`}>
                            Changes
                          </span>
                        )}
                      </div>
                      {gitStatus.last_commit && (
                        <div className={`text-sm ${
                          darkMode ? 'text-[#969696]' : 'text-gray-600'
                        }`}>
                          Last commit: {gitStatus.last_commit.message} 
                          <span className="ml-2">({gitStatus.last_commit.hash})</span>
                        </div>
                      )}
                    </div>

                    {/* File Changes */}
                    {((gitStatus.modified_files?.length || 0) > 0 || 
                      (gitStatus.added_files?.length || 0) > 0 || 
                      (gitStatus.deleted_files?.length || 0) > 0 || 
                      (gitStatus.untracked_files?.length || 0) > 0) && (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <h3 className={`font-medium ${
                            darkMode ? 'text-[#cccccc]' : 'text-gray-900'
                          }`}>Changes</h3>
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              onClick={() => handleAddFiles(selectedFiles.size > 0 ? selectedFiles : null)}
                              className={`${
                                darkMode 
                                  ? 'bg-[#0e639c] text-white hover:bg-[#1177bb]' 
                                  : 'bg-gray-900 text-white hover:bg-gray-800'
                              }`}
                            >
                              {selectedFiles.size > 0 ? `Add Selected (${selectedFiles.size})` : 'Add All'}
                            </Button>
                            {selectedFiles.size > 0 && (
                              <Button
                                size="sm"
                                onClick={() => setShowCommitInput(true)}
                                className="bg-green-600 text-white hover:bg-green-700"
                              >
                                Commit
                              </Button>
                            )}
                          </div>
                        </div>

                        {/* Modified Files */}
                        {(gitStatus.modified_files?.length || 0) > 0 && (
                          <div>
                            <h4 className={`text-sm font-medium mb-2 ${
                              darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                            }`}>Modified</h4>
                            <div className="space-y-1">
                              {gitStatus.modified_files?.map((file) => (
                                <div
                                  key={file}
                                  onClick={() => toggleFileSelection(file)}
                                  className={`flex items-center gap-2 p-2 rounded cursor-pointer transition-colors ${
                                    selectedFiles.has(file)
                                      ? darkMode ? 'bg-[#0e639c] bg-opacity-20' : 'bg-blue-50'
                                      : darkMode ? 'hover:bg-[#2d2d30]' : 'hover:bg-gray-50'
                                  }`}
                                >
                                  <AlertCircle className="w-4 h-4 text-yellow-500" />
                                  <FileText className="w-4 h-4" />
                                  <span className={`text-sm ${
                                    darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                                  }`}>{file}</span>
                                  {selectedFiles.has(file) && (
                                    <Check className="w-4 h-4 text-green-500 ml-auto" />
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Untracked Files */}
                        {(gitStatus.untracked_files?.length || 0) > 0 && (
                          <div>
                            <h4 className={`text-sm font-medium mb-2 ${
                              darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                            }`}>Untracked</h4>
                            <div className="space-y-1">
                              {gitStatus.untracked_files?.map((file) => (
                                <div
                                  key={file}
                                  onClick={() => toggleFileSelection(file)}
                                  className={`flex items-center gap-2 p-2 rounded cursor-pointer transition-colors ${
                                    selectedFiles.has(file)
                                      ? darkMode ? 'bg-[#0e639c] bg-opacity-20' : 'bg-blue-50'
                                      : darkMode ? 'hover:bg-[#2d2d30]' : 'hover:bg-gray-50'
                                  }`}
                                >
                                  <PlusCircle className="w-4 h-4 text-green-500" />
                                  <FileText className="w-4 h-4" />
                                  <span className={`text-sm ${
                                    darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                                  }`}>{file}</span>
                                  {selectedFiles.has(file) && (
                                    <Check className="w-4 h-4 text-green-500 ml-auto" />
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Commit Input */}
                    {showCommitInput && (
                      <div className={`p-4 rounded-lg border ${
                        darkMode ? 'bg-[#2d2d30] border-[#3e3e42]' : 'bg-gray-50 border-gray-200'
                      }`}>
                        <input
                          type="text"
                          value={commitMessage}
                          onChange={(e) => setCommitMessage(e.target.value)}
                          placeholder="Enter commit message..."
                          className={`w-full px-3 py-2 rounded border ${
                            darkMode 
                              ? 'bg-[#1e1e1e] border-[#3e3e42] text-[#cccccc]' 
                              : 'bg-white border-gray-300 text-gray-900'
                          }`}
                        />
                        <div className="flex gap-2 mt-2">
                          <Button
                            size="sm"
                            onClick={handleCommit}
                            className="bg-green-600 text-white hover:bg-green-700"
                          >
                            Commit Changes
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setShowCommitInput(false)}
                            className={`${
                              darkMode 
                                ? 'bg-[#3e3e42] text-[#cccccc] hover:bg-[#2d2d30]' 
                                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                            }`}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'branches' && (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className={`font-medium ${
                        darkMode ? 'text-[#cccccc]' : 'text-gray-900'
                      }`}>Branch Management</h3>
                      <Button
                        size="sm"
                        onClick={() => setShowBranchInput(true)}
                        className={`${
                          darkMode 
                            ? 'bg-[#0e639c] text-white hover:bg-[#1177bb]' 
                            : 'bg-gray-900 text-white hover:bg-gray-800'
                        }`}
                      >
                        New Branch
                      </Button>
                    </div>

                    {showBranchInput && (
                      <div className={`p-4 rounded-lg border ${
                        darkMode ? 'bg-[#2d2d30] border-[#3e3e42]' : 'bg-gray-50 border-gray-200'
                      }`}>
                        <input
                          type="text"
                          value={branchName}
                          onChange={(e) => setBranchName(e.target.value)}
                          placeholder="Enter branch name..."
                          className={`w-full px-3 py-2 rounded border ${
                            darkMode 
                              ? 'bg-[#1e1e1e] border-[#3e3e42] text-[#cccccc]' 
                              : 'bg-white border-gray-300 text-gray-900'
                          }`}
                        />
                        <div className="flex gap-2 mt-2">
                          <Button
                            size="sm"
                            onClick={handleCreateBranch}
                            className="bg-green-600 text-white hover:bg-green-700"
                          >
                            Create Branch
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setShowBranchInput(false)}
                            className={`${
                              darkMode 
                                ? 'bg-[#3e3e42] text-[#cccccc] hover:bg-[#2d2d30]' 
                                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                            }`}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    )}

                    <div className="space-y-2">
                      <div className={`text-xs font-medium uppercase tracking-wider ${darkMode ? 'text-gray-500' : 'text-gray-400'}`}>
                        All Branches
                      </div>
                      {branchLoading ? (
                        <div className="flex items-center gap-2 py-4">
                          <RefreshCw className="w-4 h-4 animate-spin" />
                          <span className="text-sm">Fetching branches...</span>
                        </div>
                      ) : (
                        <div className="grid gap-2">
                          {branches.map((b) => (
                            <div
                              key={b.full_name}
                              className={`flex items-center justify-between p-3 rounded-lg border transition-all ${
                                b.is_current
                                  ? darkMode 
                                    ? 'bg-[#0e639c]/20 border-[#0e639c] text-white' 
                                    : 'bg-blue-50 border-blue-200 text-blue-900'
                                  : darkMode
                                    ? 'bg-[#2d2d30] border-[#3e3e42] text-[#cccccc] hover:border-gray-500'
                                    : 'bg-white border-gray-200 text-gray-700 hover:border-gray-400'
                              }`}
                            >
                              <div className="flex items-center gap-3">
                                <GitBranch className={cn("w-4 h-4", b.is_current ? "text-blue-500" : "text-gray-400")} />
                                <div className="flex flex-col">
                                  <span className="text-sm font-medium">{b.name}</span>
                                  <span className={`text-[10px] uppercase tracking-wider ${
                                    b.type === 'remote' ? 'text-orange-500' : 'text-gray-500'
                                  }`}>
                                    {b.type}
                                  </span>
                                </div>
                                {b.is_current && (
                                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                                    darkMode ? 'bg-blue-500/20 text-blue-400' : 'bg-blue-100 text-blue-600'
                                  }`}>Current</span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className={`p-4 rounded-lg ${
                      darkMode ? 'bg-[#2d2d30]' : 'bg-gray-50'
                    }`}>
                      <p className={`text-sm ${
                        darkMode ? 'text-[#969696]' : 'text-gray-600'
                      }`}>
                         Branch switching is currently managed through commits. Create a new branch to start working on a parallel version.
                      </p>
                    </div>
                  </div>
                )}

                {activeTab === 'commits' && (
                  <div className="space-y-4">
                    <h3 className={`font-medium ${
                      darkMode ? 'text-[#cccccc]' : 'text-gray-900'
                    }`}>Commit History</h3>
                    <div className={`p-4 rounded-lg ${
                      darkMode ? 'bg-[#2d2d30]' : 'bg-gray-50'
                    }`}>
                      <p className={`text-sm ${
                        darkMode ? 'text-[#969696]' : 'text-gray-600'
                      }`}>
                        Commit history loading coming soon...
                      </p>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default GitPanel;
