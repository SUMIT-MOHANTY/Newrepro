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
  MinusCircle
} from 'lucide-react';
import { Button } from './ui/button';

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

  useEffect(() => {
    if (isVisible && projectId) {
      fetchGitStatus();
    }
  }, [isVisible, projectId]);

  const fetchGitStatus = async () => {
    if (!projectId) return;
    
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/git/status', {
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
      const response = await fetch('http://localhost:8000/api/git/init', {
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
      const response = await fetch('http://localhost:8000/api/git/add', {
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
      const response = await fetch('http://localhost:8000/api/git/commit', {
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

  const handleCreateBranch = async () => {
    if (!projectId || !branchName.trim()) return;
    
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/git/branch', {
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
      <div className={`w-full max-w-4xl max-h-[80vh] overflow-hidden rounded-lg shadow-2xl ${
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
        <div className="flex flex-col h-[600px]">
          {/* Tabs */}
          <div className={`flex border-b ${
            darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
          }`}>
            {['status', 'commits', 'branches'].map((tab) => (
              <Button
                key={tab}
                variant="ghost"
                onClick={() => setActiveTab(tab)}
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
            ) : !gitStatus ? (
              <div className="text-center py-8">
                <GitBranch className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p className={`mb-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`}>
                  No Git repository found
                </p>
                <Button
                  onClick={handleGitInit}
                  className={`${
                    darkMode 
                      ? 'bg-[#0e639c] text-white hover:bg-[#1177bb]' 
                      : 'bg-gray-900 text-white hover:bg-gray-800'
                  }`}
                >
                  Initialize Repository
                </Button>
              </div>
            ) : (
              <>
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
                    {(gitStatus.modified_files.length > 0 || 
                      gitStatus.added_files.length > 0 || 
                      gitStatus.deleted_files.length > 0 || 
                      gitStatus.untracked_files.length > 0) && (
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
                        {gitStatus.modified_files.length > 0 && (
                          <div>
                            <h4 className={`text-sm font-medium mb-2 ${
                              darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                            }`}>Modified</h4>
                            <div className="space-y-1">
                              {gitStatus.modified_files.map((file) => (
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
                        {gitStatus.untracked_files.length > 0 && (
                          <div>
                            <h4 className={`text-sm font-medium mb-2 ${
                              darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                            }`}>Untracked</h4>
                            <div className="space-y-1">
                              {gitStatus.untracked_files.map((file) => (
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

                    <div className={`p-4 rounded-lg ${
                      darkMode ? 'bg-[#2d2d30]' : 'bg-gray-50'
                    }`}>
                      <div className="flex items-center gap-2 mb-3">
                        <GitBranch className="w-4 h-4" />
                        <span className={`font-medium ${
                          darkMode ? 'text-[#cccccc]' : 'text-gray-900'
                        }`}>
                          Current: {gitStatus.branch}
                        </span>
                      </div>
                      <p className={`text-sm ${
                        darkMode ? 'text-[#969696]' : 'text-gray-600'
                      }`}>
                        Branch switching and management coming soon...
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
