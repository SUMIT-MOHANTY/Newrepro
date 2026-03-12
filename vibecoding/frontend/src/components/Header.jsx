import React from 'react';
import { Sun, Moon, GitBranch } from 'lucide-react';

const Header = ({ darkMode, onToggleTheme, onPublish, onGitClick }) => {
  return (
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
          onClick={onGitClick}
          className={`p-2 rounded-lg transition-colors ${
            darkMode 
              ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
              : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
          }`}
          title="Git Integration"
        >
          <GitBranch className="w-4 h-4" />
        </button>
        <button
          onClick={onToggleTheme}
          className={`p-2 rounded-lg transition-colors ${
            darkMode 
              ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
              : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
          }`}
        >
          {darkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>
        <button 
          onClick={onPublish}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            darkMode 
              ? 'bg-[#0e639c] text-white hover:bg-[#1177bb]' 
              : 'bg-gray-900 text-white hover:bg-gray-800'
          }`}
        >
          Publish
        </button>
      </div>
    </div>
  );
};

export default Header;
