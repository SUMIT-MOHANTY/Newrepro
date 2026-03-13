import React from 'react';
import { Sun, Moon, GitBranch } from 'lucide-react';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';

const Header = ({ darkMode, onToggleTheme, onPublish, onGitClick }) => {
  return (
    <div className={cn(
      'flex items-center justify-between px-6 py-3 border-b',
      darkMode ? 'bg-[#252526] border-[#3e3e42]' : 'bg-white border-gray-200'
    )}>
      <div className="flex items-center gap-3">
        <img src="/logo.png" alt="Bourtec" className="h-8 w-auto" />
        <span className={cn(
          'text-base font-semibold',
          darkMode ? 'text-[#cccccc]' : 'text-gray-900'
        )}>VibeCoding</span>
      </div>
      
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={onGitClick}
          className={cn(
            'rounded-lg',
            darkMode 
              ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
              : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
          )}
          title="Git Integration"
        >
          <GitBranch className="w-4 h-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleTheme}
          className={cn(
            'rounded-lg',
            darkMode ? 'text-[#cccccc] hover:text-white' : 'text-gray-600 hover:text-gray-900'
          )}
        >
          {darkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </Button>
        <Button 
          onClick={onPublish}
          className={cn(
            'px-4 py-2 rounded-lg text-sm font-medium',
            darkMode 
              ? 'bg-[#0e639c] text-white hover:bg-[#1177bb]' 
              : 'bg-gray-900 text-white hover:bg-gray-800'
          )}
        >
          Publish
        </Button>
      </div>
    </div>
  );
};

export default Header;
