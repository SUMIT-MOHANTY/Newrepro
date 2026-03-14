import React from 'react';
import { Zap, Plus, History, RefreshCw, Check, LogOut } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from './ui/button';
import bourntecLogo from '../../assets/bourntec_logo.png';

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
  codeVersions = [],
  currentCodeVersion = 1,
  setCurrentCodeVersion,
  formatTimestamp,
}) => {
  const [showVersionHistory, setShowVersionHistory] = React.useState(false);

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
            <span className="text-sm text-gray-400 whitespace-nowrap">Chat v{chatVersion}</span>
            
            {codeVersions.length > 0 && (
              <div className="relative version-history-container ml-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowVersionHistory(!showVersionHistory)}
                  className="flex items-center gap-2 bg-white/5 hover:bg-white/10 text-white h-8 py-0 px-3"
                >
                  <History className="w-3.5 h-3.5" />
                  <span className="text-xs">Code v{currentCodeVersion}/{codeVersions.length}</span>
                </Button>
                
                {showVersionHistory && (
                  <div className="absolute top-full left-0 mt-2 w-80 bg-[#1a1a1f] border border-white/10 rounded-lg shadow-2xl z-50 max-h-[70vh] overflow-y-auto backdrop-blur-md">
                    <div className="p-3 border-b border-white/10 sticky top-0 bg-[#1a1a1f]/90 backdrop-blur-sm z-10">
                      <div className="text-xs font-semibold text-white uppercase tracking-wider">Code Version History</div>
                      <div className="text-[10px] text-gray-400 mt-1">{codeVersions.length} versions saved</div>
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
                          className={`w-full text-left px-3 py-2.5 h-auto rounded-lg mb-1 transition-all ${
                            currentCodeVersion === version.version
                              ? 'bg-purple-600/20 border border-purple-500/30'
                              : 'hover:bg-white/5 border border-transparent'
                          }`}
                        >
                          <div className="w-full">
                            <div className="flex items-center justify-between mb-1">
                              <span className={`text-xs font-bold ${
                                currentCodeVersion === version.version ? 'text-purple-300' : 'text-white'
                              }`}>
                                Version {version.version}
                              </span>
                              <span className="text-[10px] text-gray-500">
                                {formatTimestamp(version.timestamp)}
                              </span>
                            </div>
                            <div className="text-[11px] text-gray-400 line-clamp-2 leading-relaxed italic">
                              "{version.prompt}"
                            </div>
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
    </div>
  );
};

export default Header;
