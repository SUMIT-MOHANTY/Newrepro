import { useState, useEffect } from 'react';
import { 
  GitBranch, 
  Plus, 
  RefreshCw,
  X,
  Check,
  AlertCircle,
  FileText,
  PlusCircle,
  Sparkles,
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
  projectId
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
  const [commits, setCommits] = useState([]);
  const [commitsLoading, setCommitsLoading] = useState(false);

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
      if (activeTab === 'commits') {
        fetchCommits();
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

  const fetchCommits = async () => {
    if (!projectId) return;
    
    setCommitsLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/git/commits`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId })
      });
      const data = await response.json();
      if (data.status === 'success') {
        setCommits(data.commits || []);
      }
    } catch (error) {
      console.error('Error fetching commits:', error);
    } finally {
      setCommitsLoading(false);
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
        fetchCommits();
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
    
    // Validate that remote is configured
    if (!remoteUrl) {
      alert('Please configure a remote repository in the Settings tab first.');
      setActiveTab('settings');
      return;
    }
    
    // Validate that token is provided
    if (!token) {
      alert('Please provide a Personal Access Token in the Settings tab for authentication.');
      setActiveTab('settings');
      return;
    }
    
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
        alert('✅ Push successful! Your changes have been pushed to the remote repository.');
      } else {
        const errorMsg = data.stderr || data.message || 'Unknown error';
        
        // Provide helpful error messages
        if (errorMsg.includes('authentication failed') || errorMsg.includes('could not read Username')) {
          alert('❌ Authentication failed. Please check your Personal Access Token in Settings.');
          setActiveTab('settings');
        } else if (errorMsg.includes('repository not found') || errorMsg.includes('does not appear to be')) {
          alert('❌ Repository not found. Please verify the repository URL in Settings.');
          setActiveTab('settings');
        } else if (errorMsg.includes('permission denied') || errorMsg.includes('access')) {
          alert('❌ Permission denied. Make sure your token has push access to this repository.');
          setActiveTab('settings');
        } else {
          alert(`❌ Push failed: ${errorMsg}`);
        }
      }
    } catch (error) {
      console.error('Error pushing:', error);
      alert('❌ Network error. Please check your connection and try again.');
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0, 0, 0, 0.75)', backdropFilter: 'blur(8px)' }}>
      <div 
        className="w-full max-w-5xl max-h-[92vh] flex flex-col overflow-hidden rounded-3xl shadow-2xl animate-in fade-in zoom-in-95 duration-300"
        style={{
          background: darkMode 
            ? 'linear-gradient(135deg, rgba(20, 20, 35, 0.95) 0%, rgba(15, 15, 25, 0.98) 100%)'
            : 'linear-gradient(135deg, rgba(255, 255, 255, 0.98) 0%, rgba(245, 245, 250, 0.95) 100%)',
          border: darkMode ? '1px solid rgba(255, 255, 255, 0.08)' : '1px solid rgba(0, 0, 0, 0.08)',
          backdropFilter: 'blur(40px)',
          boxShadow: darkMode 
            ? '0 0 0 1px rgba(255, 255, 255, 0.05), 0 25px 60px -12px rgba(0, 0, 0, 0.6), 0 0 120px -40px rgba(139, 92, 246, 0.2)'
            : '0 0 0 1px rgba(0, 0, 0, 0.05), 0 25px 60px -12px rgba(0, 0, 0, 0.25)'
        }}
      >
        {/* Header */}
        <div 
          className="flex items-center justify-between px-8 py-5 border-b relative"
          style={{
            borderColor: darkMode ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)',
            background: darkMode 
              ? 'linear-gradient(135deg, rgba(139, 92, 246, 0.08) 0%, rgba(236, 72, 153, 0.05) 100%)'
              : 'linear-gradient(135deg, rgba(139, 92, 246, 0.03) 0%, rgba(236, 72, 153, 0.02) 100%)'
          }}
        >
          <div className="flex items-center gap-4">
            <div 
              className="w-12 h-12 rounded-xl flex items-center justify-center"
              style={{
                background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                boxShadow: '0 4px 20px rgba(139, 92, 246, 0.3)'
              }}
            >
              <GitBranch className="w-6 h-6 text-white" />
            </div>
            <div>
              <h2 
                className="text-xl font-bold tracking-tight"
                style={{
                  background: darkMode 
                    ? 'linear-gradient(135deg, #fff 30%, rgba(255, 255, 255, 0.7) 100%)'
                    : 'linear-gradient(135deg, #1a1a1a 30%, rgba(0, 0, 0, 0.7) 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text'
                }}
              >
                Git Integration
              </h2>
              <p className="text-xs" style={{ color: darkMode ? 'rgba(255, 255, 255, 0.4)' : 'rgba(0, 0, 0, 0.4)' }}>
                Version control for your project
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchGitStatus}
              disabled={loading}
              className="p-2.5 rounded-xl transition-all duration-200 hover:scale-105 active:scale-95"
              style={{
                background: darkMode ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.04)',
                border: darkMode ? '1px solid rgba(255, 255, 255, 0.08)' : '1px solid rgba(0, 0, 0, 0.08)',
                color: darkMode ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.7)'
              }}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={handlePush}
              disabled={loading || pushLoading || !gitStatus}
              className="px-4 py-2.5 rounded-xl font-semibold text-sm flex items-center gap-2 transition-all duration-200 hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: 'linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%)',
                color: 'white',
                boxShadow: '0 4px 15px rgba(139, 92, 246, 0.3)'
              }}
            >
              <Upload className={`w-4 h-4 ${pushLoading ? 'animate-bounce' : ''}`} />
              {pushLoading ? 'Pushing...' : 'Push'}
            </button>
            <button
              onClick={onClose}
              className="p-2.5 rounded-xl transition-all duration-200 hover:scale-105 active:scale-95"
              style={{
                background: darkMode ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.04)',
                border: darkMode ? '1px solid rgba(255, 255, 255, 0.08)' : '1px solid rgba(0, 0, 0, 0.08)',
                color: darkMode ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.7)'
              }}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex flex-col flex-1 min-h-0">
          {/* Tabs */}
          <div 
            className="flex gap-1 px-6 pt-4"
            style={{
              borderBottom: darkMode ? '1px solid rgba(255, 255, 255, 0.06)' : '1px solid rgba(0, 0, 0, 0.06)'
            }}
          >
            {['status', 'commits', 'branches', 'settings'].map((tab) => (
              <button
                key={tab}
                onClick={() => {
                  setActiveTab(tab);
                  if (tab === 'branches') fetchBranches();
                  if (tab === 'status') fetchGitStatus();
                  if (tab === 'commits') fetchCommits();
                }}
                className="px-5 py-3 rounded-t-xl capitalize text-sm font-semibold transition-all duration-200 relative"
                style={{
                  background: activeTab === tab
                    ? darkMode
                      ? 'linear-gradient(135deg, rgba(139, 92, 246, 0.15) 0%, rgba(236, 72, 153, 0.1) 100%)'
                      : 'linear-gradient(135deg, rgba(139, 92, 246, 0.08) 0%, rgba(236, 72, 153, 0.05) 100%)'
                    : 'transparent',
                  color: activeTab === tab
                    ? darkMode ? '#c4b5fd' : '#8B5CF6'
                    : darkMode ? 'rgba(255, 255, 255, 0.5)' : 'rgba(0, 0, 0, 0.5)',
                  borderBottom: activeTab === tab
                    ? darkMode ? '2px solid #8B5CF6' : '2px solid #8B5CF6'
                    : '2px solid transparent'
                }}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-y-auto p-8">
            {loading ? (
              <div className="flex flex-col items-center justify-center h-64 gap-4">
                <RefreshCw className="w-8 h-8 animate-spin" style={{ color: '#8B5CF6' }} />
                <p className="text-sm" style={{ color: darkMode ? 'rgba(255, 255, 255, 0.5)' : 'rgba(0, 0, 0, 0.5)' }}>
                  Loading...
                </p>
              </div>
            ) : (!gitStatus || gitStatus.status === 'not_initialized') ? (
              <div className="text-center py-12">
                <div 
                  className="w-24 h-24 rounded-3xl mx-auto mb-8 flex items-center justify-center relative overflow-hidden"
                  style={{
                    background: darkMode 
                      ? 'linear-gradient(135deg, rgba(139, 92, 246, 0.15) 0%, rgba(236, 72, 153, 0.1) 100%)'
                      : 'linear-gradient(135deg, rgba(139, 92, 246, 0.08) 0%, rgba(236, 72, 153, 0.05) 100%)',
                    border: darkMode ? '1px solid rgba(139, 92, 246, 0.2)' : '1px solid rgba(139, 92, 246, 0.15)'
                  }}
                >
                  <GitBranch className="w-12 h-12" style={{ color: '#8B5CF6' }} />
                </div>
                <h3 
                  className="text-2xl font-bold mb-3"
                  style={{
                    background: darkMode 
                      ? 'linear-gradient(135deg, #fff 30%, rgba(255, 255, 255, 0.7) 100%)'
                      : 'linear-gradient(135deg, #1a1a1a 30%, rgba(0, 0, 0, 0.7) 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    backgroundClip: 'text'
                  }}
                >
                  Version Control
                </h3>
                <div className="flex items-center justify-center gap-2 mb-10 h-6">
                  <Sparkles className="w-4 h-4" style={{ color: '#8B5CF6', opacity: 0.7 }} />
                  <p className="text-sm" style={{ color: darkMode ? 'rgba(255, 255, 255, 0.5)' : 'rgba(0, 0, 0, 0.5)' }}>
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
                <button
                  onClick={handleGitInit}
                  className="px-8 py-4 rounded-2xl font-bold text-base flex items-center gap-3 mx-auto transition-all duration-300 hover:scale-105 active:scale-95"
                  style={{
                    background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                    color: 'white',
                    boxShadow: '0 8px 30px rgba(139, 92, 246, 0.4)'
                  }}
                >
                  <Plus className="w-5 h-5" />
                  Initialize Repository
                </button>
              </div>
              ) : (
                <>
                  {activeTab === 'settings' && (
                    <div className="space-y-6 max-w-3xl mx-auto">
                      <div 
                        className="p-8 rounded-2xl"
                        style={{
                          background: darkMode 
                            ? 'rgba(255, 255, 255, 0.03)'
                            : 'rgba(0, 0, 0, 0.02)',
                          border: darkMode ? '1px solid rgba(255, 255, 255, 0.08)' : '1px solid rgba(0, 0, 0, 0.08)'
                        }}
                      >
                        <div className="flex items-center gap-3 mb-8">
                          <div 
                            className="w-10 h-10 rounded-xl flex items-center justify-center"
                            style={{
                              background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(139, 92, 246, 0.15) 100%)',
                              border: '1px solid rgba(59, 130, 246, 0.3)'
                            }}
                          >
                            <Globe className="w-5 h-5" style={{ color: '#3B82F6' }} />
                          </div>
                          <div>
                            <h3 
                              className="text-lg font-bold"
                              style={{ color: darkMode ? 'white' : '#1a1a1a' }}
                            >
                              Remote Repository
                            </h3>
                            <p className="text-xs" style={{ color: darkMode ? 'rgba(255, 255, 255, 0.4)' : 'rgba(0, 0, 0, 0.4)' }}>
                              Connect to GitHub, GitLab, or any Git remote
                            </p>
                          </div>
                        </div>
                        
                        <div className="space-y-5">
                          <div>
                            <label 
                              className="block text-xs font-bold mb-2 uppercase tracking-wider"
                              style={{ color: darkMode ? 'rgba(255, 255, 255, 0.5)' : 'rgba(0, 0, 0, 0.5)' }}
                            >
                              Repository URL
                            </label>
                            <input
                              type="text"
                              value={remoteUrl}
                              onChange={(e) => setRemoteUrl(e.target.value)}
                              placeholder="https://github.com/username/repo.git"
                              className="w-full px-4 py-3.5 rounded-xl transition-all outline-none"
                              style={{
                                background: darkMode ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.03)',
                                border: darkMode ? '1.5px solid rgba(255, 255, 255, 0.08)' : '1.5px solid rgba(0, 0, 0, 0.08)',
                                color: darkMode ? 'white' : '#1a1a1a'
                              }}
                              onFocus={(e) => {
                                e.target.style.borderColor = '#8B5CF6';
                                e.target.style.boxShadow = darkMode 
                                  ? '0 0 0 4px rgba(139, 92, 246, 0.1)'
                                  : '0 0 0 4px rgba(139, 92, 246, 0.08)';
                              }}
                              onBlur={(e) => {
                                e.target.style.borderColor = darkMode ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)';
                                e.target.style.boxShadow = 'none';
                              }}
                            />
                          </div>
                          
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label 
                                className="block text-xs font-bold mb-2 uppercase tracking-wider"
                                style={{ color: darkMode ? 'rgba(255, 255, 255, 0.5)' : 'rgba(0, 0, 0, 0.5)' }}
                              >
                                Username (Optional)
                              </label>
                              <input
                                type="text"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                placeholder="git-user"
                                className="w-full px-4 py-3.5 rounded-xl transition-all outline-none"
                                style={{
                                  background: darkMode ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.03)',
                                  border: darkMode ? '1.5px solid rgba(255, 255, 255, 0.08)' : '1.5px solid rgba(0, 0, 0, 0.08)',
                                  color: darkMode ? 'white' : '#1a1a1a'
                                }}
                                onFocus={(e) => {
                                  e.target.style.borderColor = '#8B5CF6';
                                  e.target.style.boxShadow = darkMode 
                                    ? '0 0 0 4px rgba(139, 92, 246, 0.1)'
                                    : '0 0 0 4px rgba(139, 92, 246, 0.08)';
                                }}
                                onBlur={(e) => {
                                  e.target.style.borderColor = darkMode ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)';
                                  e.target.style.boxShadow = 'none';
                                }}
                              />
                            </div>
                            <div>
                              <label 
                                className="block text-xs font-bold mb-2 uppercase tracking-wider"
                                style={{ color: darkMode ? 'rgba(255, 255, 255, 0.5)' : 'rgba(0, 0, 0, 0.5)' }}
                              >
                                Access Token
                              </label>
                              <div className="relative">
                                <Key 
                                  className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
                                  style={{ color: darkMode ? 'rgba(255, 255, 255, 0.3)' : 'rgba(0, 0, 0, 0.3)' }}
                                />
                                <input
                                  type="password"
                                  value={token}
                                  onChange={(e) => setToken(e.target.value)}
                                  placeholder="ghp_xxxxxxxxxxxx"
                                  className="w-full pl-10 pr-4 py-3.5 rounded-xl transition-all outline-none"
                                  style={{
                                    background: darkMode ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.03)',
                                    border: darkMode ? '1.5px solid rgba(255, 255, 255, 0.08)' : '1.5px solid rgba(0, 0, 0, 0.08)',
                                    color: darkMode ? 'white' : '#1a1a1a'
                                  }}
                                  onFocus={(e) => {
                                    e.target.style.borderColor = '#8B5CF6';
                                    e.target.style.boxShadow = darkMode 
                                      ? '0 0 0 4px rgba(139, 92, 246, 0.1)'
                                      : '0 0 0 4px rgba(139, 92, 246, 0.08)';
                                  }}
                                  onBlur={(e) => {
                                    e.target.style.borderColor = darkMode ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)';
                                    e.target.style.boxShadow = 'none';
                                  }}
                                />
                              </div>
                            </div>
                          </div>
                          
                          <div className="pt-3">
                            <button
                              onClick={handleSaveRemote}
                              disabled={loading || !remoteUrl}
                              className="w-full py-3.5 rounded-xl font-bold transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
                              style={{
                                background: 'linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%)',
                                color: 'white',
                                boxShadow: '0 4px 20px rgba(139, 92, 246, 0.3)'
                              }}
                            >
                              Save Remote Settings
                            </button>
                          </div>
                        </div>
                      </div>

                      <div 
                        className="p-5 rounded-2xl flex items-start gap-4"
                        style={{
                          background: darkMode 
                            ? 'rgba(245, 158, 11, 0.08)'
                            : 'rgba(245, 158, 11, 0.05)',
                          border: darkMode ? '1px solid rgba(245, 158, 11, 0.2)' : '1px solid rgba(245, 158, 11, 0.15)'
                        }}
                      >
                        <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" style={{ color: '#F59E0B' }} />
                        <div className="space-y-1">
                          <p className="text-sm font-bold" style={{ color: darkMode ? '#FCD34D' : '#D97706' }}>
                            Security Note
                          </p>
                          <p className="text-xs leading-relaxed" style={{ color: darkMode ? 'rgba(252, 211, 77, 0.7)' : 'rgba(217, 119, 6, 0.8)' }}>
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
                    <div className="flex items-center justify-between">
                      <h3 className={`font-medium ${
                        darkMode ? 'text-[#cccccc]' : 'text-gray-900'
                      }`}>Commit History</h3>
                      <button
                        onClick={fetchCommits}
                        disabled={commitsLoading}
                        className="p-2 rounded-lg transition-all duration-200 hover:scale-105 active:scale-95"
                        style={{
                          background: darkMode ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.04)',
                          border: darkMode ? '1px solid rgba(255, 255, 255, 0.08)' : '1px solid rgba(0, 0, 0, 0.08)',
                          color: darkMode ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.7)'
                        }}
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${commitsLoading ? 'animate-spin' : ''}`} />
                      </button>
                    </div>
                    {commitsLoading ? (
                      <div className="flex items-center gap-2 py-8 justify-center">
                        <RefreshCw className="w-5 h-5 animate-spin" style={{ color: '#8B5CF6' }} />
                        <span className="text-sm" style={{ color: darkMode ? 'rgba(255, 255, 255, 0.5)' : 'rgba(0, 0, 0, 0.5)' }}>
                          Loading commits...
                        </span>
                      </div>
                    ) : commits.length === 0 ? (
                      <div className={`p-6 rounded-xl text-center ${
                        darkMode ? 'bg-[#2d2d30]' : 'bg-gray-50'
                      }`}>
                        <p className={`text-sm ${
                          darkMode ? 'text-[#969696]' : 'text-gray-600'
                        }`}>
                          No commits yet. Stage and commit files to see history here.
                        </p>
                      </div>
                    ) : (
                      <div className="relative">
                        <div 
                          className="absolute left-[19px] top-3 bottom-3 w-px"
                          style={{ background: darkMode ? 'rgba(139, 92, 246, 0.2)' : 'rgba(139, 92, 246, 0.15)' }}
                        />
                        <div className="space-y-1">
                          {commits.map((commit, index) => (
                            <div
                              key={commit.hash}
                              className="flex items-start gap-4 p-3 rounded-xl transition-all duration-200 group relative"
                              style={{
                                background: index === 0 
                                  ? darkMode 
                                    ? 'rgba(139, 92, 246, 0.06)' 
                                    : 'rgba(139, 92, 246, 0.03)'
                                  : 'transparent'
                              }}
                            >
                              <div 
                                className="w-[10px] h-[10px] rounded-full mt-1.5 shrink-0 z-10 ring-2"
                                style={{
                                  background: index === 0 ? '#8B5CF6' : darkMode ? '#4a4a4a' : '#d1d5db',
                                  ringColor: index === 0 
                                    ? 'rgba(139, 92, 246, 0.3)' 
                                    : darkMode ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)',
                                  borderColor: index === 0 
                                    ? 'rgba(139, 92, 246, 0.3)' 
                                    : darkMode ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)'
                                }}
                              />
                              <div className="flex-1 min-w-0">
                                <p 
                                  className="text-sm font-medium truncate"
                                  style={{ color: darkMode ? '#e5e5e5' : '#1a1a1a' }}
                                >
                                  {commit.message}
                                </p>
                                <div className="flex items-center gap-3 mt-1">
                                  <span 
                                    className="text-xs font-mono px-1.5 py-0.5 rounded"
                                    style={{ 
                                      background: darkMode ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.04)',
                                      color: darkMode ? 'rgba(255, 255, 255, 0.5)' : 'rgba(0, 0, 0, 0.45)'
                                    }}
                                  >
                                    {commit.hash?.substring(0, 7)}
                                  </span>
                                  <span 
                                    className="text-xs"
                                    style={{ color: darkMode ? 'rgba(255, 255, 255, 0.4)' : 'rgba(0, 0, 0, 0.4)' }}
                                  >
                                    {commit.author}
                                  </span>
                                  <span 
                                    className="text-xs"
                                    style={{ color: darkMode ? 'rgba(255, 255, 255, 0.3)' : 'rgba(0, 0, 0, 0.3)' }}
                                  >
                                    {commit.date}
                                  </span>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
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
