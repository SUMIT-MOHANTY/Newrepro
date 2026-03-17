import React from 'react';
import { Zap, Plus, History, RefreshCw, Check, LogOut, Folder, ChevronDown, LayoutGrid } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from './ui/button';
import bourntecLogo from '../../assets/bourntec_logo.png';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const Header = ({
  chatVersion,
  user,
  showUserMenu,
  setShowUserMenu,
  onNewChat,
  onGitClick,
  onDeploy,
  isDeploying,
  deployStatus,
  previewCode,
  loading,
  onLogout,
  projects = [],
  currentProjectId,
  setCurrentProjectId,
  showProjectDropdown,
  setShowProjectDropdown,
  branches = [],
  currentBranch = 'main',
  onBranchSwitch,
  formatTimestamp,
  onCreateProject,
}) => {
  const [showVersionHistory, setShowVersionHistory] = React.useState(false);
  const [showProjectModal, setShowProjectModal] = React.useState(false);
  const [projectName, setProjectName] = React.useState('');
  const navigate = useNavigate();

  const handleCreateProject = async () => {
    if (!projectName.trim()) return;
    
    try {
      const response = await axios.post(`${API_BASE_URL}/api/projects`, { name: projectName.trim() }, {
        headers: { Authorization: `Bearer ${localStorage.getItem('vibecoding_token')}` }
      });
      
      const newProjectId = response.data.project_id;
      setCurrentProjectId(newProjectId);
      localStorage.setItem('vibecoding_workspace_id', newProjectId);
      setShowProjectDropdown(false);
      setShowProjectModal(false);
      setProjectName('');
      
      // Call parent callback to clear chat
      if (onCreateProject) {
        onCreateProject(newProjectId);
      }
      
      window.location.href = `/a/${newProjectId}`;
    } catch (error) {
      console.error('Failed to create project:', error);
    }
  };

  const currentProject = projects.find(p => p.project_id === currentProjectId) || { name: 'Select Project' };

  return (
    <div className="h-14 border-b border-white/10 flex items-center justify-between px-6 bg-[#0F0F14]">
      {/* Left Side - Bourntec Logo + VibeCoding Branding */}
      <div className="flex items-center gap-3">
        <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
          <img
            src={bourntecLogo}
            alt="Bourntec"
            className="h-7 w-auto"
          />
          <div className="h-6 w-px bg-white/10" />
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-base text-white">VibeCoding</span>
          </div>
        </Link>
        
        {user && (
          <>
            <div className="h-6 w-px bg-white/10" />
            
            {/* Project Selection Dropdown */}
            <div className="relative project-dropdown-container">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowProjectDropdown(!showProjectDropdown)}
                className="flex items-center gap-2 bg-white/5 hover:bg-white/10 text-white h-9 px-3 border border-white/10"
              >
                <Folder className="w-4 h-4 text-purple-400" />
                <span className="text-sm font-medium truncate max-w-[150px]">{currentProject.name}</span>
                <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${showProjectDropdown ? 'rotate-180' : ''}`} />
              </Button>

              {showProjectDropdown && (
                <div className="absolute top-full left-0 mt-2 w-64 bg-[#1a1a1f] border border-white/10 rounded-xl shadow-2xl z-[100] backdrop-blur-md animate-in fade-in slide-in-from-top-2 duration-200">
                  <div className="p-3 border-b border-white/10 flex items-center justify-between">
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">Your Projects</span>
                    <button 
                      onClick={() => setShowProjectModal(true)}
                      className="p-1.5 rounded-lg bg-purple-600/20 text-purple-400 hover:bg-purple-600/30 transition-colors"
                      title="Create New Project"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                  
                  <div className="p-2 max-h-[400px] overflow-y-auto">
                    {projects.length === 0 ? (
                      <div className="py-8 px-4 text-center">
                        <LayoutGrid className="w-8 h-8 text-gray-600 mx-auto mb-2 opacity-50" />
                        <p className="text-xs text-gray-500">No projects found</p>
                      </div>
                    ) : (
                      projects.map((project) => (
                        <button
                          key={project.project_id}
                          onClick={() => {
                            localStorage.setItem('vibecoding_workspace_id', project.project_id);
                            window.location.href = `/a/${project.project_id}`;
                          }}
                          className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all mb-1 ${
                            currentProjectId === project.project_id
                              ? 'bg-purple-600/20 border border-purple-500/30 text-purple-300'
                              : 'hover:bg-white/5 border border-transparent text-gray-400 hover:text-white'
                          }`}
                        >
                          <div className={`w-2 h-2 rounded-full ${currentProjectId === project.project_id ? 'bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.5)]' : 'bg-gray-700'}`} />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium truncate">{project.name}</div>
                            <div className="text-[10px] opacity-50 truncate">{project.project_id}</div>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                  
                  <div className="p-2 border-t border-white/10">
                    {/* <button
                      onClick={() => setShowProjectModal(true)}
                      className="w-full flex items-center justify-center gap-2 py-2 text-xs font-bold text-white bg-gradient-to-r from-purple-600 to-pink-600 rounded-lg hover:from-purple-700 hover:to-pink-700 transition-all shadow-lg active:scale-95"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Create New Project
                    </button> */}
                  </div>
                </div>
              )}
            </div>

            <div className="h-6 w-px bg-white/10" />
            
            {branches.length > 0 && (
              <div className="relative version-history-container ml-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowVersionHistory(!showVersionHistory)}
                  className="flex items-center gap-2 bg-white/5 hover:bg-white/10 text-white h-8 py-0 px-3"
                >
                  <History className="w-3.5 h-3.5" />
                  <span className="text-xs">
                    {branches.findIndex(b => b.version_id === currentBranch) >= 0 
                      ? `Version ${branches.findIndex(b => b.version_id === currentBranch) + 1}`
                      : currentBranch}
                  </span>
                  <ChevronDown className={`w-3 h-3 transition-transform ${showVersionHistory ? 'rotate-180' : ''}`} />
                </Button>
                
                {showVersionHistory && (
                  <div className="absolute top-full left-0 mt-2 w-80 bg-[#1a1a1f] border border-white/10 rounded-lg shadow-2xl z-50 max-h-[70vh] overflow-y-auto backdrop-blur-md">
                    <div className="p-3 border-b border-white/10 sticky top-0 bg-[#1a1a1f]/90 backdrop-blur-sm z-10">
                      <div className="text-xs font-semibold text-white uppercase tracking-wider">Versions</div>
                      <div className="text-[10px] text-gray-400 mt-1">{branches.length} versions • Checkpoints shown in chat</div>
                    </div>
                    <div className="p-2">
                      {branches.map((branch, index) => (
                        <Button
                          key={branch.version_id}
                          variant="ghost"
                          onClick={() => {
                            onBranchSwitch(branch.version_id);
                            setShowVersionHistory(false);
                          }}
                          className={`w-full text-left px-3 py-2.5 h-auto rounded-lg mb-1 transition-all ${
                            currentBranch === branch.version_id
                              ? 'bg-purple-600/20 border border-purple-500/30'
                              : 'hover:bg-white/5 border border-transparent'
                          }`}
                        >
                          <div className="w-full">
                            <div className="flex items-center justify-between mb-1">
                              <div className="flex items-center gap-2">
                                <span className={`text-xs font-bold ${
                                  currentBranch === branch.version_id ? 'text-purple-300' : 'text-white'
                                }`}>
                                  Version {index + 1}
                                </span>
                                {branch.is_current && (
                                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-green-600/20 text-green-400 font-mono">
                                    current
                                  </span>
                                )}
                              </div>
                              <span className="text-[10px] text-gray-500">
                                {branch.commit_count} commits
                              </span>
                            </div>
                            {branch.latest_commit && (
                              <div className="text-[11px] text-gray-400 line-clamp-2 leading-relaxed italic">
                                "{branch.latest_commit.message}"
                              </div>
                            )}
                          </div>
                        </Button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Right Side - Actions (Only shown if user is logged in) */}
      {user && (
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={onNewChat}
            className="bg-white/5 hover:bg-white/10 text-white"
            title="Start a new chat"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onGitClick}
            className="bg-white/5 hover:bg-white/10 text-white"
            title="Git Integration"
          >
            <History className="w-4 h-4" />
            Git
          </Button>
          <Button
            disabled={isDeploying || !previewCode}
            onClick={onDeploy}
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

          {/* User Avatar + Menu */}
          <div className="user-menu-container" style={{ position: 'relative' }}>
            <button
              className="user-avatar-btn"
              onClick={() => setShowUserMenu(!showUserMenu)}
              id="user-menu-trigger"
            >
              <div
                className="user-avatar"
                style={{ background: user?.avatar_color || '#8B5CF6' }}
              >
                {(user?.full_name || user?.username || 'U').charAt(0).toUpperCase()}
              </div>
              <div className="user-info">
                <span className="user-name">{user?.full_name || user?.username}</span>
                <span className="user-email">{user?.email}</span>
              </div>
            </button>
            {showUserMenu && (
              <div className="user-menu-dropdown">
                <div style={{ padding: '10px 14px' }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'rgba(255,255,255,0.8)' }}>
                    {user?.full_name || user?.username}
                  </div>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>
                    {user?.email}
                  </div>
                </div>
                <div className="user-menu-divider" />
                <button
                  className="user-menu-item danger"
                  onClick={() => { setShowUserMenu(false); onLogout(); }}
                  id="logout-btn"
                >
                  <LogOut size={16} />
                  Sign Out
                </button>
              </div>
            )}
          </div>
        </div>
      )}
      
      {/* Project Creation Modal */}
      {showProjectModal && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[#1a1a1f] border border-white/10 rounded-2xl shadow-2xl w-full max-w-md mx-4 animate-in zoom-in-95 duration-200">
            <div className="p-6 border-b border-white/10">
              <h2 className="text-xl font-bold text-white">Create New Project</h2>
              <p className="text-sm text-gray-400 mt-1">Enter a name for your new project</p>
            </div>
            
            <div className="p-6">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Project Name
              </label>
              <input
                type="text"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && projectName.trim()) {
                    handleCreateProject();
                  } else if (e.key === 'Escape') {
                    setShowProjectModal(false);
                    setProjectName('');
                  }
                }}
                placeholder="My Awesome Project"
                autoFocus
                className="w-full px-4 py-3 bg-[#0F0F14] border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            
            <div className="p-6 pt-0 flex items-center gap-3">
              <Button
                variant="ghost"
                onClick={() => {
                  setShowProjectModal(false);
                  setProjectName('');
                }}
                className="flex-1 bg-white/5 hover:bg-white/10 text-white"
              >
                Cancel
              </Button>
              <Button
                onClick={handleCreateProject}
                disabled={!projectName.trim()}
                className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Create Project
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Header;
