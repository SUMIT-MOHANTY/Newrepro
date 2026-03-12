import { useState, useMemo } from 'react';
import { ChevronRight, ChevronDown, File, Folder, FolderOpen } from 'lucide-react';

// Helper function to detect filename from code (defined outside component)
const detectFilename = (code) => {
  if (!code) return 'code.txt';
  if (code.includes('from flask') || code.includes('Flask(')) return 'app.py';
  if (code.includes('from django')) return 'app.py';
  if (code.includes('from fastapi')) return 'app.py';
  if (code.includes('<!DOCTYPE') || code.includes('<html')) return 'index.html';
  if (code.includes('import React') || code.includes('from react')) return 'App.jsx';
  if (code.includes('export default') && code.includes('function')) return 'index.js';
  return 'code.txt';
};

// Helper function to build tree from files (defined outside component)
const buildTree = (files) => {
  const root = { type: 'folder', name: 'src', children: {}, expanded: true };
  
  Object.entries(files).forEach(([path, content]) => {
    const parts = path.split('/');
    let current = root;
    
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;
      
      if (isLast) {
        current.children[part] = {
          type: 'file',
          name: part,
          path: path,
          content: content
        };
      } else {
        if (!current.children[part]) {
          current.children[part] = {
            type: 'folder',
            name: part,
            children: {}
          };
        }
        current = current.children[part];
      }
    }
  });
  
  return root;
};

const FileTree = ({ code, darkMode, onFileSelect, selectedFile }) => {
  const [expandedFolders, setExpandedFolders] = useState(new Set(['src']));

  // Parse code to extract file structure
  const fileStructure = useMemo(() => {
    if (!code) return null;

    // Check if code contains file markers
    const fileMarkers = code.match(/\/\/\s*FILE:\s*(.+)|#\s*FILE:\s*(.+)|<!--\s*FILE:\s*(.+)\s*-->/gi);
    
    if (fileMarkers && fileMarkers.length > 0) {
      // Multi-file structure
      const files = {};
      const parts = code.split(/\/\/\s*FILE:\s*|#\s*FILE:\s*|<!--\s*FILE:\s*|\s*-->/gi);
      
      for (let i = 1; i < parts.length; i += 2) {
        const filename = parts[i].trim();
        const content = parts[i + 1] || '';
        files[filename] = content.trim();
      }
      
      return buildTree(files);
    } else {
      // Single file - detect type
      const filename = detectFilename(code);
      return {
        type: 'file',
        name: filename,
        path: filename,
        content: code
      };
    }
  }, [code]);

  const toggleFolder = (path) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const renderTree = (node, path = '', level = 0) => {
    if (!node) return null;

    if (node.type === 'file') {
      const isSelected = selectedFile === node.path;
      return (
        <div
          key={path}
          onClick={() => onFileSelect(node)}
          className={`flex items-center gap-2 px-2 py-1 cursor-pointer text-sm ${
            isSelected
              ? darkMode ? 'bg-[#37373d] text-white' : 'bg-blue-50 text-blue-600'
              : darkMode ? 'text-[#cccccc] hover:bg-[#2d2d30]' : 'text-gray-700 hover:bg-gray-100'
          }`}
          style={{ paddingLeft: `${level * 12 + 8}px` }}
        >
          <File className="w-4 h-4 flex-shrink-0" />
          <span className="truncate">{node.name}</span>
        </div>
      );
    }

    if (node.type === 'folder') {
      const isExpanded = expandedFolders.has(path);
      const Icon = isExpanded ? FolderOpen : Folder;
      const ChevronIcon = isExpanded ? ChevronDown : ChevronRight;

      return (
        <div key={path}>
          <div
            onClick={() => toggleFolder(path)}
            className={`flex items-center gap-2 px-2 py-1 cursor-pointer text-sm ${
              darkMode ? 'text-[#cccccc] hover:bg-[#2d2d30]' : 'text-gray-700 hover:bg-gray-100'
            }`}
            style={{ paddingLeft: `${level * 12 + 8}px` }}
          >
            <ChevronIcon className="w-4 h-4 flex-shrink-0" />
            <Icon className="w-4 h-4 flex-shrink-0" />
            <span className="truncate font-medium">{node.name}</span>
          </div>
          {isExpanded && node.children && (
            <div>
              {Object.entries(node.children).map(([name, child]) =>
                renderTree(child, `${path}/${name}`, level + 1)
              )}
            </div>
          )}
        </div>
      );
    }

    return null;
  };

  if (!fileStructure) {
    return (
      <div className={`h-full flex items-center justify-center p-4 ${
        darkMode ? 'text-[#858585]' : 'text-gray-400'
      }`}>
        <p className="text-sm">No files to display</p>
      </div>
    );
  }

  // Single file case
  if (fileStructure.type === 'file') {
    return (
      <div className="h-full">
        <div
          onClick={() => onFileSelect(fileStructure)}
          className={`flex items-center gap-2 px-2 py-1 cursor-pointer text-sm ${
            darkMode ? 'bg-[#37373d] text-white' : 'bg-blue-50 text-blue-600'
          }`}
        >
          <File className="w-4 h-4 flex-shrink-0" />
          <span className="truncate">{fileStructure.name}</span>
        </div>
      </div>
    );
  }

  // Multi-file tree
  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      {renderTree(fileStructure, 'src', 0)}
    </div>
  );
};

export default FileTree;
