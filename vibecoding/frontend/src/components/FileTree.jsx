import { useState, useMemo, useEffect } from 'react';
import { ChevronRight, ChevronDown, File, Folder, FolderOpen, Lock, Unlock } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/vibecoding';

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

const FileTree = ({ code, darkMode, onFileSelect, selectedFile, projectId }) => {
  const [expandedFolders, setExpandedFolders] = useState(new Set(['src']));
  const [frozenFiles, setFrozenFiles] = useState([]);
  const [loading, setLoading] = useState(false);

  // Fetch frozen files when projectId changes
  useEffect(() => {
    if (projectId) {
      fetchFrozenFiles();
    }
  }, [projectId]);

  const fetchFrozenFiles = async () => {
    if (!projectId) return;
    
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/frozen-files`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setFrozenFiles(data.frozen_files || []);
      }
    } catch (error) {
      console.error('Failed to fetch frozen files:', error);
    }
  };

  const toggleFileFrozen = async (filePath, e) => {
    e.stopPropagation();
    if (!projectId) return;
    
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const isFrozen = frozenFiles.includes(filePath);
      
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/frozen-files`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          file_path: filePath,
          frozen: !isFrozen
        })
      });
      
      if (response.ok) {
        // Update local state
        if (isFrozen) {
          setFrozenFiles(frozenFiles.filter(f => f !== filePath));
        } else {
          setFrozenFiles([...frozenFiles, filePath]);
        }
      }
    } catch (error) {
      console.error('Failed to toggle file frozen status:', error);
    } finally {
      setLoading(false);
    }
  };

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
      const isFrozen = frozenFiles.includes(node.path);
      const FreezeIcon = isFrozen ? Lock : Unlock;
      
      return (
        <div
          key={path}
          className={`flex items-center gap-2 px-2 py-1 cursor-pointer text-sm group ${
            isSelected
              ? darkMode ? 'bg-[#37373d] text-white' : 'bg-blue-50 text-blue-600'
              : darkMode ? 'text-[#cccccc] hover:bg-[#2d2d30]' : 'text-gray-700 hover:bg-gray-100'
          }`}
          style={{ paddingLeft: `${level * 12 + 8}px` }}
        >
          <div className="flex items-center gap-2 flex-1" onClick={() => onFileSelect(node)}>
            <File className="w-4 h-4 flex-shrink-0" />
            <span className="truncate">{node.name}</span>
          </div>
          {projectId && (
            <button
              onClick={(e) => toggleFileFrozen(node.path, e)}
              disabled={loading}
              className={`p-1 rounded ${
                isFrozen
                  ? 'text-yellow-500 hover:text-yellow-600'
                  : `opacity-0 group-hover:opacity-100 transition-opacity ${darkMode ? 'text-gray-400 hover:text-gray-300' : 'text-gray-500 hover:text-gray-600'}`
              }`}
              title={isFrozen ? 'File is frozen (read-only)' : 'Click to freeze file'}
            >
              <FreezeIcon className="w-3.5 h-3.5" />
            </button>
          )}
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
    const isFrozen = frozenFiles.includes(fileStructure.path);
    const FreezeIcon = isFrozen ? Lock : Unlock;
    
    return (
      <div className="h-full">
        <div
          className={`flex items-center gap-2 px-2 py-1 cursor-pointer text-sm group ${
            darkMode ? 'bg-[#37373d] text-white' : 'bg-blue-50 text-blue-600'
          }`}
        >
          <div className="flex items-center gap-2 flex-1" onClick={() => onFileSelect(fileStructure)}>
            <File className="w-4 h-4 flex-shrink-0" />
            <span className="truncate">{fileStructure.name}</span>
          </div>
          {projectId && (
            <button
              onClick={(e) => toggleFileFrozen(fileStructure.path, e)}
              disabled={loading}
              className={`p-1 rounded ${
                isFrozen
                  ? 'text-yellow-500 hover:text-yellow-600'
                  : `opacity-0 group-hover:opacity-100 transition-opacity ${darkMode ? 'text-gray-400 hover:text-gray-300' : 'text-gray-500 hover:text-gray-600'}`
              }`}
              title={isFrozen ? 'File is frozen (read-only)' : 'Click to freeze file'}
            >
              <FreezeIcon className="w-3.5 h-3.5" />
            </button>
          )}
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
