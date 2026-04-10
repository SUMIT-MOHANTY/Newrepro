import React from 'react';
import { Zap, Plus, History, RefreshCw, Check, LogOut, Folder, ChevronDown, LayoutGrid, Sun, Moon, Rocket } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from './ui/button';
import bourntecLogo from '../../assets/bourntec_logo.png';
import bourntecLogoLight from '../../assets/bourntec_logo_l.png';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/vibecoding';

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
  darkMode,
  setDarkMode,
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

      window.location.href = `/vibecoding/a/${newProjectId}`;
    } catch (error) {
      console.error('Failed to create project:', error);
    }
  };

  const currentProject = projects.find(p => p.project_id === currentProjectId) || { name: 'Select Project' };

  return (
    <div className={`h-14 border-b flex items-center justify-between px-6 transition-colors ${
      darkMode ? 'border-white/10 bg-[#0F0F14]' : 'border-gray-200 bg-white'
    }`}>
      {/* Left Side - Bourntec Logo + VibeCoding Branding */}
      <div className="flex items-center gap-3">
        <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
          <img
            src={darkMode ? bourntecLogo : bourntecLogoLight}
            alt="Bourntec"
            className="h-7 w-auto transition-all"
          />
          <div className={`h-6 w-px ${darkMode ? 'bg-white/10' : 'bg-gray-200'}`} />
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <span className={`font-bold text-base ${darkMode ? 'text-white' : 'text-gray-900'}`}>VibeCoding</span>
          </div>
        </Link>

        {user && (
          <>
            <div className={`h-6 w-px ${darkMode ? 'bg-white/10' : 'bg-gray-200'}`} />

            {/* Project Selection Dropdown */}
            <div className="relative project-dropdown-container">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowProjectDropdown(!showProjectDropdown)}
                className={`flex items-center gap-2 h-9 px-3 border transition-all ${
                  darkMode 
                    ? 'bg-white/5 hover:bg-white/10 text-white border-white/10' 
                    : 'bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-200'
                }`}
              >
                <Folder className="w-4 h-4 text-purple-400" />
                <span className="text-sm font-medium truncate max-w-[150px]">{currentProject.name}</span>
                <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${showProjectDropdown ? 'rotate-180' : ''}`} />
              </Button>

              {showProjectDropdown && (
                <div className={`absolute top-full left-0 mt-2 w-64 border rounded-xl shadow-2xl z-[100] backdrop-blur-md animate-in fade-in slide-in-from-top-2 duration-200 ${
                  darkMode ? 'bg-[#1a1a1f] border-white/10' : 'bg-white border-gray-200'
                }`}>
                  <div className={`p-3 border-b flex items-center justify-between ${darkMode ? 'border-white/10' : 'border-gray-100'}`}>
                    <span className={`text-xs font-bold uppercase tracking-widest ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>Your Projects</span>
                    <button
                      onClick={() => setShowProjectModal(true)}
                      className="p-1.5 rounded-lg bg-purple-600/20 text-purple-400 hover:bg-purple-600/30 transition-colors"
                      title="Create New Project"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="p-2 max-h-[400px] overflow-y-auto custom-scrollbar">
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
                            window.location.href = `/vibecoding/a/${project.project_id}`;
                          }}
                          className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all mb-1 ${currentProjectId === project.project_id
                              ? (darkMode ? 'bg-purple-600/20 border border-purple-500/30 text-purple-300' : 'bg-purple-50 border border-purple-100 text-purple-700')
                              : (darkMode ? 'hover:bg-white/5 border border-transparent text-gray-400 hover:text-white' : 'hover:bg-gray-100 border border-transparent text-gray-600 hover:text-gray-900')
                            }`}
                        >
                          <div className={`w-2 h-2 rounded-full ${currentProjectId === project.project_id ? 'bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.5)]' : (darkMode ? 'bg-gray-700' : 'bg-gray-300')}`} />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium truncate">{project.name}</div>
                            <div className="text-[10px] opacity-50 truncate">{project.project_id}</div>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className={`h-6 w-px ${darkMode ? 'bg-white/10' : 'bg-gray-200'}`} />

            {branches.length > 0 && (
              <div className="relative version-history-container ml-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowVersionHistory(!showVersionHistory)}
                  className={`flex items-center gap-2 h-8 py-0 px-3 transition-all ${
                    darkMode 
                      ? 'bg-white/5 hover:bg-white/10 text-white' 
                      : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
                  }`}
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
                  <div className={`absolute top-full left-0 mt-2 w-80 border rounded-lg shadow-2xl z-50 max-h-[70vh] overflow-y-auto backdrop-blur-md custom-scrollbar ${
                    darkMode ? 'bg-[#1a1a1f] border-white/10' : 'bg-white border-gray-200'
                  }`}>
                    <div className={`p-3 border-b sticky top-0 backdrop-blur-sm z-10 ${
                      darkMode ? 'border-white/10 bg-[#1a1a1f]/90 text-white' : 'border-gray-100 bg-white/90 text-gray-900'
                    }`}>
                      <div className="text-xs font-semibold uppercase tracking-wider">Versions</div>
                      <div className={`text-[10px] mt-1 ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>{branches.length} versions • Snapshots shown in chat</div>
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
                          className={`w-full text-left px-3 py-2.5 h-auto rounded-lg mb-1 transition-all ${currentBranch === branch.version_id
                              ? (darkMode ? 'bg-purple-600/20 border border-purple-500/30' : 'bg-purple-50 border border-purple-100')
                              : (darkMode ? 'hover:bg-white/5 border border-transparent' : 'hover:bg-gray-100 border border-transparent')
                            }`}
                        >
                          <div className="w-full">
                            <div className="flex items-center justify-between mb-1">
                              <div className="flex items-center gap-2">
                                <span className={`text-xs font-bold ${currentBranch === branch.version_id 
                                  ? (darkMode ? 'text-purple-300' : 'text-purple-700') 
                                  : (darkMode ? 'text-white' : 'text-gray-900')
                                  }`}>
                                  Version {index + 1}
                                </span>
                                {branch.is_current && (
                                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-green-600/20 text-green-400 font-mono">
                                    active
                                  </span>
                                )}
                              </div>
                              <span className="text-[10px] text-gray-500">
                                {branch.commit_count} snapshots
                              </span>
                            </div>
                            {branch.latest_commit && (
                              <div className={`text-[11px] line-clamp-2 leading-relaxed italic ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>
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
            className={`transition-all ${
              darkMode ? 'bg-white/5 hover:bg-white/10 text-white' : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
            }`}
            title="Start a new chat"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onGitClick}
            className={`transition-all ${
              darkMode ? 'bg-white/5 hover:bg-white/10 text-white' : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
            }`}
            title="Git Integration"
          >
            <History className="w-4 h-4" />
            Git
          </Button>

          <Button
            variant="ghost"
            size="icon"
            onClick={() => setDarkMode(!darkMode)}
            className={`h-9 w-9 rounded-lg transition-all ${
              darkMode ? 'bg-white/5 hover:bg-white/10 text-yellow-400' : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
            }`}
            title={darkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          >
            {darkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </Button>
          <Button
            size="sm"
            onClick={onDeploy}
            disabled={isDeploying || !previewCode || loading}
            className={`transition-all duration-300 min-w-[100px] h-9 shadow-lg font-bold flex items-center justify-center gap-2 ${
              deployStatus === 'success' ? 'bg-green-600 hover:bg-green-700 text-white' :
              deployStatus === 'error' ? 'bg-red-600 hover:bg-red-700 text-white' :
              'bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white shadow-purple-500/20'
            } active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {isDeploying ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Publishing...</span>
              </>
            ) : deployStatus === 'success' ? (
              <>
                <Check className="w-4 h-4" />
                <span>Published</span>
              </>
            ) : deployStatus === 'error' ? (
              <>
                <Zap className="w-4 h-4" />
                <span>Failed</span>
              </>
            ) : (
              <>
                <Rocket className="w-4 h-4" />
                <span>Publish</span>
              </>
            )}
          </Button>

          {/* User Avatar + Menu */}
          <div className="user-menu-container" style={{ position: 'relative' }}>
            <button
              className={`user-avatar-btn flex items-center gap-2 px-2 py-1 rounded-lg transition-colors ${
                darkMode ? 'hover:bg-white/5' : 'hover:bg-gray-100'
              }`}
              onClick={() => setShowUserMenu(!showUserMenu)}
              id="user-menu-trigger"
            >
              <div
                className="user-avatar w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold text-sm shadow-sm"
                style={{ background: user?.avatar_color || '#8B5CF6' }}
              >
                {(user?.full_name || user?.username || 'U').charAt(0).toUpperCase()}
              </div>
              <div className="user-info flex flex-col justify-center text-left hidden sm:block">
                <div className={`user-name text-xs font-bold leading-none ${darkMode ? 'text-white' : 'text-gray-900'}`}>
                  {user?.full_name || user?.username}
                </div>
                {user?.email && (
                  <div className={`user-email text-[10px] leading-tight mt-0.5 ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                    {user?.email}
                  </div>
                )}
              </div>
            </button>
            {showUserMenu && (
              <div className={`user-menu-dropdown absolute top-full right-0 mt-2 w-56 border rounded-xl shadow-2xl z-[100] backdrop-blur-md animate-in fade-in slide-in-from-top-2 duration-200 ${
                darkMode ? 'bg-[#1a1a1f] border-white/10' : 'bg-white border-gray-200'
              }`}>
                <div className="p-3">
                  <div className={`text-sm font-bold ${darkMode ? 'text-white' : 'text-gray-900'}`}>
                    {user?.full_name || user?.username}
                  </div>
                  <div className={`text-xs mt-1 ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                    {user?.email}
                  </div>
                </div>
                <div className={`h-px ${darkMode ? 'bg-white/10' : 'bg-gray-100'}`} />
                <div className="p-1">
                  <button
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors ${
                      darkMode ? 'text-red-400 hover:bg-red-400/10' : 'text-red-600 hover:bg-red-50'
                    }`}
                    onClick={() => { setShowUserMenu(false); onLogout(); }}
                    id="logout-btn"
                  >
                    <LogOut size={16} />
                    Sign Out
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Project Creation Modal */}
      {showProjectModal && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className={`border rounded-2xl shadow-2xl w-full max-w-md mx-4 animate-in zoom-in-95 duration-200 overflow-hidden ${
            darkMode ? 'bg-[#1a1a1f] border-white/10' : 'bg-white border-gray-200'
          }`}>
            <div className={`p-6 border-b ${darkMode ? 'border-white/10' : 'border-gray-100'}`}>
              <h2 className={`text-xl font-bold ${darkMode ? 'text-white' : 'text-gray-900'}`}>Create New Project</h2>
              <p className={`text-sm mt-1 ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>Enter a name for your new project</p>
            </div>

            <div className="p-6">
              <label className={`block text-sm font-medium mb-2 ${darkMode ? 'text-gray-300' : 'text-gray-700'}`}>
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
                className={`w-full px-4 py-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all ${
                  darkMode 
                    ? 'bg-[#0F0F14] border-white/10 text-white placeholder-gray-500' 
                    : 'bg-gray-50 border-gray-200 text-gray-900 placeholder-gray-400'
                }`}
              />
            </div>

            <div className="p-6 pt-0 flex items-center gap-3">
              <Button
                variant="ghost"
                onClick={() => {
                  setShowProjectModal(false);
                  setProjectName('');
                }}
                className={`flex-1 transition-all ${
                  darkMode ? 'bg-white/5 hover:bg-white/10 text-white' : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
                }`}
              >
                Cancel
              </Button>
              <Button
                onClick={handleCreateProject}
                disabled={!projectName.trim()}
                className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white disabled:opacity-50 disabled:cursor-not-allowed shadow-lg"
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
