import React, { useRef } from 'react';
import { Eye, Code, Copy, Check, RefreshCw, Download, Sparkles } from 'lucide-react';
import { Button } from './ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { cn } from '@/lib/utils';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from './ui/select';
import FileTree from './FileTree';
import EditElementMenu from './EditElementMenu';

const CodePreview = ({
  previewCode,
  activeTab,
  setActiveTab,
  darkMode,
  copied,
  onCopyCode,
  onRefreshPreview,
  onDownloadCode,
  codeVersions,
  selectedVersion,
  onLoadVersion,
  containerPreviewUrl,  // Add container preview URL prop
  onSendElementToAI,   // New prop for sending element to AI
  onUpdateCode         // New prop for updating code when element is edited
}) => {
  const iframeRef = useRef(null);
  const [iframeKey, setIframeKey] = React.useState(0);
  const [isLoading, setIsLoading] = React.useState(false);
  const [deviceMode, setDeviceMode] = React.useState('desktop'); // desktop, tablet, mobile
  const [isFullscreen, setIsFullscreen] = React.useState(false);
  const [selectedFile, setSelectedFile] = React.useState(null);
  const [currentFileContent, setCurrentFileContent] = React.useState('');
  const [editMenu, setEditMenu] = React.useState({
    visible: false,
    element: null,
    position: { x: 0, y: 0 }
  });

  // Force iframe refresh when containerPreviewUrl or previewCode changes
  React.useEffect(() => {
    setIsLoading(true);
    setIframeKey(prev => prev + 1);
  }, [containerPreviewUrl, previewCode]);

  // Initialize selected file when code changes
  React.useEffect(() => {
    if (previewCode && !selectedFile) {
      // Auto-select first file
      setCurrentFileContent(previewCode);
    }
  }, [previewCode, selectedFile]);

  const handleFileSelect = (file) => {
    setSelectedFile(file.path);
    setCurrentFileContent(file.content);
  };

  // Handle refresh button click
  const handleRefresh = () => {
    setIsLoading(true);
    setIframeKey(prev => prev + 1);
    if (onRefreshPreview) {
      onRefreshPreview();
    }
  };

  // Handle iframe load
  const handleIframeLoad = () => {
    setIsLoading(false);
    console.log('🌐 iframe loaded with src:', containerPreviewUrl || 'data URL');

    // Add element selection functionality to iframe
    const iframe = iframeRef.current;
    if (iframe && iframe.contentDocument) {
      const doc = iframe.contentDocument;

      // Add click handler to all elements
      const addClickHandlers = () => {
        const allElements = doc.querySelectorAll('*');
        allElements.forEach(element => {
          element.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            showEditMenu(element, e);
          });

          // Add hover effect
          element.addEventListener('mouseenter', () => {
            element.style.outline = '2px solid #3b82f6';
            element.style.outlineOffset = '2px';
          });

          element.addEventListener('mouseleave', () => {
            element.style.outline = '';
            element.style.outlineOffset = '';
          });
        });
      };

      // Initial setup
      addClickHandlers();

      // Watch for DOM changes
      const observer = new MutationObserver(() => {
        addClickHandlers();
      });

      observer.observe(doc.body, {
        childList: true,
        subtree: true
      });
    }
  };

  // Show edit menu
  const showEditMenu = (element, event) => {
    const rect = element.getBoundingClientRect();
    setEditMenu({
      visible: true,
      element: element,
      position: {
        x: rect.left + rect.width / 2,
        y: rect.top
      }
    });
  };

  // Handle element property changes
  const handleEditProperties = (element, property, value) => {
    element.style[property] = value;

    // Update the code in the parent
    if (onUpdateCode) {
      const iframe = iframeRef.current;
      if (iframe && iframe.contentDocument) {
        const updatedHTML = iframe.contentDocument.documentElement.outerHTML;
        onUpdateCode(updatedHTML);
      }
    }
  };

  // Handle element code editing
  const handleEditCode = (element) => {
    const currentHTML = element.outerHTML;
    const newHTML = prompt('Edit HTML:', currentHTML);
    if (newHTML !== null && newHTML !== currentHTML) {
      element.outerHTML = newHTML;

      // Update the code in the parent
      if (onUpdateCode) {
        const iframe = iframeRef.current;
        if (iframe && iframe.contentDocument) {
          const updatedHTML = iframe.contentDocument.documentElement.outerHTML;
          onUpdateCode(updatedHTML);
        }
      }
    }
  };

  // Handle sending element to AI
  const handleSendElementToAI = (elementInfo) => {
    if (onSendElementToAI) {
      onSendElementToAI(elementInfo);
    }
  };

  // Handle element deletion
  const handleDeleteElement = (element) => {
    element.remove();

    // Update the code in the parent
    if (onUpdateCode) {
      const iframe = iframeRef.current;
      if (iframe && iframe.contentDocument) {
        const updatedHTML = iframe.contentDocument.documentElement.outerHTML;
        onUpdateCode(updatedHTML);
      }
    }
  };

  // Get device dimensions
  const getDeviceDimensions = () => {
    switch (deviceMode) {
      case 'mobile':
        return { width: '375px', height: '100%' };
      case 'tablet':
        return { width: '768px', height: '100%' };
      default:
        return { width: '100%', height: '100%' };
    }
  };

  const deviceDimensions = getDeviceDimensions();

  // Format code with proper indentation
  const formatCode = (code) => {
    if (!code) return '';

    try {
      let formatted = code;
      let indent = 0;
      const lines = formatted.split('\n');
      const formattedLines = lines.map(line => {
        const trimmed = line.trim();

        if (trimmed.startsWith('</') || trimmed.startsWith('}') || trimmed.startsWith(']')) {
          indent = Math.max(0, indent - 1);
        }

        const indentedLine = '  '.repeat(indent) + trimmed;

        if (trimmed.startsWith('<') && !trimmed.startsWith('</') && !trimmed.endsWith('/>') && !trimmed.includes('</')) {
          indent++;
        } else if (trimmed.endsWith('{') || trimmed.endsWith('[')) {
          indent++;
        }

        return indentedLine;
      });

      return formattedLines.join('\n');
    } catch {
      return code;
    }
  };

  return (
    <div className={cn("flex-1 flex flex-col min-h-0 bg-[#0A0A0F] text-white", darkMode && "dark")} style={{ position: 'relative', overflow: 'hidden' }}>
      {/* Tab Bar - Always Visible */}
      <div
        className="flex items-center gap-2 px-6 py-2 border-b flex-shrink-0"
        style={{
          backgroundColor: darkMode ? '#1e1e1e' : '#f9fafb',
          borderColor: darkMode ? '#333333' : '#e5e7eb',
          minHeight: '48px',
          width: '100%'
        }}
      >
        <div className="flex bg-[#2d2d30] p-1 rounded-lg">
          <Button
            onClick={() => setActiveTab('preview')}
            variant="ghost"
            size="sm"
            className={cn(
              'rounded-md text-xs h-8 px-3 transition-all',
              activeTab === 'preview'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-[#858585] hover:text-white hover:bg-white/5'
            )}
            disabled={!previewCode}
          >
            <Eye className="w-3.5 h-3.5 mr-1.5" />
            Preview
          </Button>
          <Button
            onClick={() => setActiveTab('code')}
            variant="ghost"
            size="sm"
            className={cn(
              'rounded-md text-xs h-8 px-3 transition-all',
              activeTab === 'code'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-[#858585] hover:text-white hover:bg-white/5'
            )}
            disabled={!previewCode}
          >
            <Code className="w-3.5 h-3.5 mr-1.5" />
            Code
          </Button>
        </div>

        <div className="ml-auto flex items-center gap-2" style={{ minWidth: '200px' }}>
          {/* Version Selector - Always visible when code exists */}
          <div className="flex items-center gap-2">
            <span className={cn(
              'text-xs whitespace-nowrap',
              darkMode ? 'text-[#858585]' : 'text-gray-500'
            )}>Version:</span>
            {previewCode && codeVersions && codeVersions.length > 0 ? (
              <Select value={String(selectedVersion || codeVersions[codeVersions.length - 1]?.id || '')} onValueChange={(val) => onLoadVersion?.(Number(val))}>
                <SelectTrigger className={cn(
                  'w-[180px] px-2 py-1 rounded-md text-xs',
                  darkMode
                    ? 'bg-[#2d2d30] text-[#cccccc] border border-[#3e3e42] hover:bg-[#3e3e42]'
                    : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
                )}>
                  <SelectValue placeholder="Select version" />
                </SelectTrigger>
                <SelectContent className={cn(
                  'z-[9999]',
                  darkMode ? 'bg-[#2d2d30] border-[#3e3e42]' : 'bg-white border-gray-300'
                )}>
                  {codeVersions.map((version, idx) => (
                    <SelectItem key={version.id} value={String(version.id)}>
                      v{codeVersions.length - idx} - {new Date(version.timestamp).toLocaleTimeString()}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <span className={cn(
                'text-xs px-2 py-1',
                darkMode ? 'text-[#858585]' : 'text-gray-400'
              )}>
                {previewCode ? 'v1 - Current' : 'No versions'}
              </span>
            )}

            <Button
              variant="ghost"
              size="icon"
              onClick={onCopyCode}
              className={cn(
                'h-8 w-8',
                darkMode
                  ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white'
                  : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
              )}
              title="Copy Code"
            >
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleRefresh}
              className={cn(
                'h-8 w-8',
                darkMode
                  ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white'
                  : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
              )}
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onDownloadCode}
              className={cn(
                'h-8 w-8',
                darkMode
                  ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white'
                  : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
              )}
              title="Download"
            >
              <Download className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Preview/Code Area */}
      <div
        className={`flex-1 min-h-0 flex flex-col overflow-hidden`}
        style={{ flex: '1 1 auto', minHeight: 0 }}
      >
        {!previewCode ? (
          <div className="flex-1 min-h-0 flex items-center justify-center">
            <div className="text-center">
              <div className={`w-20 h-20 rounded-2xl mx-auto mb-4 flex items-center justify-center ${darkMode ? 'bg-[#2d2d30]' : 'bg-gray-100'
                }`}>
                <Sparkles className={`w-10 h-10 ${darkMode ? 'text-[#858585]' : 'text-gray-400'}`} />
              </div>
              <h3 className={`text-base font-medium mb-2 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'
                }`}>
                Start building your idea
              </h3>
              <p className={`text-sm ${darkMode ? 'text-[#858585]' : 'text-gray-400'}`}>
                Describe what you want in the chat panel
              </p>
            </div>
          </div>
        ) : activeTab === 'preview' ? (
          <div className="relative w-full h-full flex flex-col">
            {/* Browser-like Top Bar */}
            <div className={`flex-shrink-0 border-b ${darkMode ? 'bg-[#252526] border-[#3e3e42]' : 'bg-gray-100 border-gray-300'
              }`}>
              {/* URL Bar */}
              <div className="flex items-center gap-2 px-4 py-2">
                {/* Navigation Buttons */}
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className={cn(
                      'h-8 w-8',
                      darkMode ? 'hover:bg-white/10' : 'hover:bg-black/10'
                    )}
                  >
                    <svg className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                    </svg>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className={cn(
                      'h-8 w-8',
                      darkMode ? 'hover:bg-white/10' : 'hover:bg-black/10'
                    )}
                  >
                    <svg className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleRefresh}
                    className={cn(
                      'h-8 w-8',
                      darkMode ? 'hover:bg-white/10' : 'hover:bg-black/10'
                    )}
                  >
                    <RefreshCw className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} />
                  </Button>
                </div>

                {/* URL Input */}
                <div className={`flex-1 flex items-center gap-2 px-3 py-1.5 rounded-lg ${darkMode ? 'bg-[#1e1e1e] border border-[#3e3e42]' : 'bg-white border border-gray-300'
                  }`}>
                  <svg className={`w-4 h-4 ${darkMode ? 'text-[#858585]' : 'text-gray-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                  <input
                    type="text"
                    value={containerPreviewUrl || 'your-app.vibecoding.app'}
                    readOnly
                    className={`flex-1 bg-transparent text-sm outline-none ${darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                      }`}
                  />
                  {containerPreviewUrl && (
                    <Button
                      size="sm"
                      onClick={() => window.open(containerPreviewUrl, '_blank')}
                      className={cn(
                        'h-6 px-2 text-xs',
                        darkMode ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-blue-500 text-white hover:bg-blue-600'
                      )}
                    >
                      Open
                    </Button>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="flex items-center gap-1">
                  {/* Device Switcher */}
                  <div className={`flex items-center gap-0.5 mr-2 p-0.5 rounded ${darkMode ? 'bg-[#1e1e1e]' : 'bg-gray-200'
                    }`}>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeviceMode('desktop')}
                      className={cn(
                        'h-8 w-8',
                        deviceMode === 'desktop'
                          ? darkMode ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-blue-500 text-white hover:bg-blue-600'
                          : darkMode ? 'text-[#858585] hover:text-[#cccccc]' : 'text-gray-500 hover:text-gray-700'
                      )}
                      title="Desktop View"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <rect x="2" y="3" width="20" height="14" rx="2" strokeWidth="2" />
                        <line x1="8" y1="21" x2="16" y2="21" strokeWidth="2" />
                        <line x1="12" y1="17" x2="12" y2="21" strokeWidth="2" />
                      </svg>
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeviceMode('tablet')}
                      className={cn(
                        'h-8 w-8',
                        deviceMode === 'tablet'
                          ? darkMode ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-blue-500 text-white hover:bg-blue-600'
                          : darkMode ? 'text-[#858585] hover:text-[#cccccc]' : 'text-gray-500 hover:text-gray-700'
                      )}
                      title="Tablet View"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <rect x="5" y="2" width="14" height="20" rx="2" strokeWidth="2" />
                        <line x1="12" y1="18" x2="12" y2="18" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeviceMode('mobile')}
                      className={cn(
                        'h-8 w-8',
                        deviceMode === 'mobile'
                          ? darkMode ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-blue-500 text-white hover:bg-blue-600'
                          : darkMode ? 'text-[#858585] hover:text-[#cccccc]' : 'text-gray-500 hover:text-gray-700'
                      )}
                      title="Mobile View"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <rect x="7" y="2" width="10" height="20" rx="2" strokeWidth="2" />
                        <line x1="12" y1="18" x2="12" y2="18" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                    </Button>
                  </div>

                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={onCopyCode}
                    className={cn(
                      'h-8 w-8',
                      darkMode ? 'hover:bg-white/10' : 'hover:bg-black/10'
                    )}
                    title="Copy Code"
                  >
                    {copied ? (
                      <Check className={`w-4 h-4 ${darkMode ? 'text-green-400' : 'text-green-600'}`} />
                    ) : (
                      <Copy className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={onDownloadCode}
                    className={cn(
                      'h-8 w-8',
                      darkMode ? 'hover:bg-white/10' : 'hover:bg-black/10'
                    )}
                    title="Download"
                  >
                    <Download className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} />
                  </Button>
                </div>
              </div>
            </div>

            {/* Preview Content */}
            <div className={`flex-1 relative flex items-center justify-center ${darkMode ? 'bg-[#1e1e1e]' : 'bg-gray-50'
              }`}>
              {isLoading && (
                <div className={`absolute inset-0 flex items-center justify-center z-10 ${darkMode ? 'bg-[#1e1e1e] bg-opacity-80' : 'bg-white bg-opacity-80'
                  }`}>
                  <div className="text-center">
                    <RefreshCw className={`w-8 h-8 animate-spin mx-auto mb-2 ${darkMode ? 'text-[#858585]' : 'text-gray-400'
                      }`} />
                    <p className={`text-sm ${darkMode ? 'text-[#858585]' : 'text-gray-500'}`}>
                      Loading preview...
                    </p>
                  </div>
                </div>
              )}
              <div
                className={`transition-all duration-300 ${deviceMode === 'desktop' ? 'w-full h-full' : 'shadow-2xl rounded-lg overflow-hidden'
                  }`}
                style={{
                  width: deviceDimensions.width,
                  height: deviceDimensions.height,
                  maxWidth: '100%',
                  maxHeight: '100%'
                }}
              >
                <iframe
                  key={iframeKey}
                  ref={iframeRef}
                  src={containerPreviewUrl ? containerPreviewUrl : `data:text/html;charset=utf-8,${encodeURIComponent(previewCode || '')}`}
                  className="w-full h-full border-0"
                  title="Preview"
                  onLoad={handleIframeLoad}
                  sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                  onError={(e) => {
                    console.error('Iframe load error:', e);
                    console.log('Attempted URL:', containerPreviewUrl);
                  }}
                />
              </div>
            </div>
          </div>
        ) : (
          // Code View with File Tree
          <div className={`flex-1 flex min-h-0 min-w-0 ${darkMode ? 'bg-[#1e1e1e]' : 'bg-gray-50'}`}>
            {/* Left Sidebar - File Tree */}
            <div className={`w-64 flex-shrink-0 border-r flex flex-col ${darkMode ? 'bg-[#151518] border-white/5' : 'bg-gray-100 border-gray-300'
               }`}>
              {/* File Tree Header */}
              <div className={`px-3 py-2 border-b ${darkMode ? 'border-white/5' : 'border-gray-300'
                }`}>
                <div className="flex items-center justify-between">
                  <span className={`text-[10px] font-bold uppercase tracking-wider ${darkMode ? 'text-[#858585]' : 'text-gray-500'
                    }`}>
                    FILES
                  </span>
                  {previewCode && (
                    <span className="ml-2 px-1.5 py-0.5 rounded bg-white/5 text-[10px] font-mono text-[#858585]">
                      {/* Detect files count from code markers if present, else 1 */}
                      {(previewCode.match(/\/\/\s*FILE:\s*|#\s*FILE:\s*|<!--\s*FILE:\s*/gi) || [1]).length}
                    </span>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={onCopyCode}
                    className={cn(
                      'h-7 w-7',
                      darkMode ? 'hover:bg-white/10' : 'hover:bg-black/10'
                    )}
                    title="Copy All Code"
                  >
                    {copied ? (
                      <Check className={`w-3.5 h-3.5 ${darkMode ? 'text-green-400' : 'text-green-600'}`} />
                    ) : (
                      <Copy className={`w-3.5 h-3.5 ${darkMode ? 'text-[#858585]' : 'text-gray-500'}`} />
                    )}
                  </Button>
                </div>
              </div>

              {/* File Tree */}
              <div className="flex-1 overflow-y-auto custom-scrollbar">
                <FileTree
                  code={previewCode}
                  darkMode={darkMode}
                  onFileSelect={handleFileSelect}
                  selectedFile={selectedFile}
                />
              </div>
            </div>

            {/* Right Side - Code Editor */}
            <div className="flex-1 flex flex-col min-w-0">
              {/* File Header */}
              <div className={`px-4 py-2 border-b flex items-center justify-between ${darkMode ? 'bg-[#151518] border-white/5' : 'bg-white border-gray-300'
                }`}>
                <div className="flex items-center gap-2">
                  <Code className={`w-4 h-4 ${darkMode ? 'text-[#858585]' : 'text-gray-500'}`} />
                  <span className={`text-sm font-medium ${darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                    }`}>
                    {selectedFile || 'Generated Code'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs ${darkMode ? 'text-[#858585]' : 'text-gray-500'
                    }`}>
                    {(currentFileContent || previewCode).split('\n').length} lines
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={onDownloadCode}
                    className={cn(
                      'h-8 w-8',
                      darkMode ? 'hover:bg-white/10' : 'hover:bg-black/10'
                    )}
                    title="Download"
                  >
                    <Download className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} />
                  </Button>
                </div>
              </div>

              {/* Code Content */}
              <div className={`flex-1 overflow-auto custom-scrollbar ${darkMode ? 'bg-[#0A0A0F]' : 'bg-white'
                }`}>
                <div className="flex min-h-full">
                  {/* Line Numbers */}
                  <div className={`py-4 px-4 select-none border-r ${darkMode ? 'bg-[#0A0A0F] text-[#444] border-white/5' : 'bg-gray-50 text-gray-400 border-gray-200'
                    }`} style={{ minWidth: '3.5rem' }}>
                    <pre className="text-xs font-mono leading-relaxed text-right">
                      {(currentFileContent || previewCode).split('\n').map((_, idx) => (
                        <div key={idx} className="h-6 flex items-center justify-end">{idx + 1}</div>
                      ))}
                    </pre>
                  </div>

                  {/* Code Content */}
                  <div className="flex-1 overflow-x-auto custom-scrollbar bg-transparent min-w-0">
                    <pre className={`py-4 px-4 text-sm font-mono leading-relaxed whitespace-pre w-fit min-w-full ${darkMode ? 'text-[#d4d4d4]' : 'text-gray-800'
                      }`}>
                      <code>{currentFileContent || previewCode}</code>
                    </pre>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Edit Element Menu */}
      {editMenu.visible && (
        <EditElementMenu
          element={editMenu.element}
          position={editMenu.position}
          onClose={() => setEditMenu({ ...editMenu, visible: false })}
          onEditProperties={handleEditProperties}
          onEditCode={handleEditCode}
          onSendToAI={handleSendElementToAI}
          onDelete={handleDeleteElement}
          darkMode={darkMode}
        />
      )}
    </div>
  );
};

export default CodePreview;
