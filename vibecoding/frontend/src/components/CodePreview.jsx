import React, { useRef } from 'react';
import { Eye, Code, Copy, Check, RefreshCw, Download, Sparkles } from 'lucide-react';
import FileTree from './FileTree';

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
  containerPreviewUrl  // Add container preview URL prop
}) => {
  const iframeRef = useRef(null);
  const [iframeKey, setIframeKey] = React.useState(0);
  const [isLoading, setIsLoading] = React.useState(false);
  const [deviceMode, setDeviceMode] = React.useState('desktop'); // desktop, tablet, mobile
  const [isFullscreen, setIsFullscreen] = React.useState(false);
  const [selectedFile, setSelectedFile] = React.useState(null);
  const [currentFileContent, setCurrentFileContent] = React.useState('');

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
    <div className="flex-1 flex flex-col">
      {/* Tab Bar */}
      <div className={`flex items-center gap-2 px-6 py-2 border-b ${
        darkMode ? 'bg-[#252526] border-[#3e3e42]' : 'bg-gray-50 border-gray-200'
      }`}>
        <button
          onClick={() => setActiveTab('preview')}
          className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'preview'
              ? darkMode
                ? 'bg-[#1e1e1e] text-white border border-[#3e3e42]'
                : 'bg-white text-gray-900 border border-gray-300 shadow-sm'
              : darkMode
                ? 'text-[#cccccc] hover:text-white hover:bg-[#2d2d30]'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          }`}
        >
          <div className="flex items-center gap-2">
            <Eye className="w-4 h-4" />
            Preview
          </div>
        </button>
        <button
          onClick={() => setActiveTab('code')}
          className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'code'
              ? darkMode
                ? 'bg-[#1e1e1e] text-white border border-[#3e3e42]'
                : 'bg-white text-gray-900 border border-gray-300 shadow-sm'
              : darkMode
                ? 'text-[#cccccc] hover:text-white hover:bg-[#2d2d30]'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          }`}
        >
          <div className="flex items-center gap-2">
            <Code className="w-4 h-4" />
            Code
          </div>
        </button>
        
        {previewCode && (
          <div className="ml-auto flex items-center gap-2">
            {/* Version Selector */}
            {codeVersions && codeVersions.length > 1 && (
              <div className="flex items-center gap-2">
                <span className={`text-xs ${
                  darkMode ? 'text-[#858585]' : 'text-gray-500'
                }`}>Version:</span>
                <select
                  value={selectedVersion || ''}
                  onChange={(e) => onLoadVersion(Number(e.target.value))}
                  className={`px-2 py-1 rounded-md text-xs transition-colors ${
                    darkMode 
                      ? 'bg-[#2d2d30] text-[#cccccc] border border-[#3e3e42] hover:bg-[#3e3e42]' 
                      : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  {codeVersions.map((version, idx) => (
                    <option key={version.id} value={version.id}>
                      v{codeVersions.length - idx} - {new Date(version.timestamp).toLocaleTimeString()}
                    </option>
                  ))}
                </select>
              </div>
            )}
            
            <button
              onClick={onCopyCode}
              className={`p-2 rounded-md transition-colors ${
                darkMode 
                  ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
                  : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
              }`}
              title="Copy Code"
            >
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </button>
            <button
              onClick={handleRefresh}
              className={`p-2 rounded-md transition-colors ${
                darkMode 
                  ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
                  : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
              }`}
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={onDownloadCode}
              className={`p-2 rounded-md transition-colors ${
                darkMode 
                  ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
                  : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
              }`}
              title="Download"
            >
              <Download className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {/* Preview/Code Area */}
      <div className={`flex-1 ${
        darkMode ? 'bg-[#1e1e1e]' : 'bg-white'
      }`}>
        {!previewCode ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <div className={`w-20 h-20 rounded-2xl mx-auto mb-4 flex items-center justify-center ${
                darkMode ? 'bg-[#2d2d30]' : 'bg-gray-100'
              }`}>
                <Sparkles className={`w-10 h-10 ${darkMode ? 'text-[#858585]' : 'text-gray-400'}`} />
              </div>
              <h3 className={`text-base font-medium mb-2 ${
                darkMode ? 'text-[#cccccc]' : 'text-gray-600'
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
            <div className={`flex-shrink-0 border-b ${
              darkMode ? 'bg-[#252526] border-[#3e3e42]' : 'bg-gray-100 border-gray-300'
            }`}>
              {/* URL Bar */}
              <div className="flex items-center gap-2 px-4 py-2">
                {/* Navigation Buttons */}
                <div className="flex items-center gap-1">
                  <button className={`p-1.5 rounded hover:bg-opacity-10 ${
                    darkMode ? 'hover:bg-white' : 'hover:bg-black'
                  }`}>
                    <svg className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                    </svg>
                  </button>
                  <button className={`p-1.5 rounded hover:bg-opacity-10 ${
                    darkMode ? 'hover:bg-white' : 'hover:bg-black'
                  }`}>
                    <svg className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                  <button 
                    onClick={handleRefresh}
                    className={`p-1.5 rounded hover:bg-opacity-10 ${
                      darkMode ? 'hover:bg-white' : 'hover:bg-black'
                    }`}
                  >
                    <RefreshCw className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} />
                  </button>
                </div>

                {/* URL Input */}
                <div className={`flex-1 flex items-center gap-2 px-3 py-1.5 rounded-lg ${
                  darkMode ? 'bg-[#1e1e1e] border border-[#3e3e42]' : 'bg-white border border-gray-300'
                }`}>
                  <svg className={`w-4 h-4 ${darkMode ? 'text-[#858585]' : 'text-gray-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                  <input
                    type="text"
                    value={containerPreviewUrl || 'your-app.vibecoding.app'}
                    readOnly
                    className={`flex-1 bg-transparent text-sm outline-none ${
                      darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                    }`}
                  />
                  {containerPreviewUrl && (
                    <button
                      onClick={() => window.open(containerPreviewUrl, '_blank')}
                      className={`text-xs px-2 py-0.5 rounded ${
                        darkMode ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-blue-500 text-white hover:bg-blue-600'
                      }`}
                    >
                      Open
                    </button>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="flex items-center gap-1">
                  {/* Device Switcher */}
                  <div className={`flex items-center gap-0.5 mr-2 p-0.5 rounded ${
                    darkMode ? 'bg-[#1e1e1e]' : 'bg-gray-200'
                  }`}>
                    <button
                      onClick={() => setDeviceMode('desktop')}
                      className={`p-1.5 rounded transition-colors ${
                        deviceMode === 'desktop'
                          ? darkMode ? 'bg-blue-600 text-white' : 'bg-blue-500 text-white'
                          : darkMode ? 'text-[#858585] hover:text-[#cccccc]' : 'text-gray-500 hover:text-gray-700'
                      }`}
                      title="Desktop View"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <rect x="2" y="3" width="20" height="14" rx="2" strokeWidth="2" />
                        <line x1="8" y1="21" x2="16" y2="21" strokeWidth="2" />
                        <line x1="12" y1="17" x2="12" y2="21" strokeWidth="2" />
                      </svg>
                    </button>
                    <button
                      onClick={() => setDeviceMode('tablet')}
                      className={`p-1.5 rounded transition-colors ${
                        deviceMode === 'tablet'
                          ? darkMode ? 'bg-blue-600 text-white' : 'bg-blue-500 text-white'
                          : darkMode ? 'text-[#858585] hover:text-[#cccccc]' : 'text-gray-500 hover:text-gray-700'
                      }`}
                      title="Tablet View"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <rect x="5" y="2" width="14" height="20" rx="2" strokeWidth="2" />
                        <line x1="12" y1="18" x2="12" y2="18" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                    </button>
                    <button
                      onClick={() => setDeviceMode('mobile')}
                      className={`p-1.5 rounded transition-colors ${
                        deviceMode === 'mobile'
                          ? darkMode ? 'bg-blue-600 text-white' : 'bg-blue-500 text-white'
                          : darkMode ? 'text-[#858585] hover:text-[#cccccc]' : 'text-gray-500 hover:text-gray-700'
                      }`}
                      title="Mobile View"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <rect x="7" y="2" width="10" height="20" rx="2" strokeWidth="2" />
                        <line x1="12" y1="18" x2="12" y2="18" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                    </button>
                  </div>

                  <button
                    onClick={onCopyCode}
                    className={`p-1.5 rounded hover:bg-opacity-10 ${
                      darkMode ? 'hover:bg-white' : 'hover:bg-black'
                    }`}
                    title="Copy Code"
                  >
                    {copied ? (
                      <Check className={`w-4 h-4 ${darkMode ? 'text-green-400' : 'text-green-600'}`} />
                    ) : (
                      <Copy className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} />
                    )}
                  </button>
                  <button
                    onClick={onDownloadCode}
                    className={`p-1.5 rounded hover:bg-opacity-10 ${
                      darkMode ? 'hover:bg-white' : 'hover:bg-black'
                    }`}
                    title="Download"
                  >
                    <Download className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} />
                  </button>
                </div>
              </div>
            </div>

            {/* Preview Content */}
            <div className={`flex-1 relative flex items-center justify-center ${
              darkMode ? 'bg-[#1e1e1e]' : 'bg-gray-50'
            }`}>
              {isLoading && (
                <div className={`absolute inset-0 flex items-center justify-center z-10 ${
                  darkMode ? 'bg-[#1e1e1e] bg-opacity-80' : 'bg-white bg-opacity-80'
                }`}>
                  <div className="text-center">
                    <RefreshCw className={`w-8 h-8 animate-spin mx-auto mb-2 ${
                      darkMode ? 'text-[#858585]' : 'text-gray-400'
                    }`} />
                    <p className={`text-sm ${darkMode ? 'text-[#858585]' : 'text-gray-500'}`}>
                      Loading preview...
                    </p>
                  </div>
                </div>
              )}
              <div 
                className={`transition-all duration-300 ${
                  deviceMode === 'desktop' ? 'w-full h-full' : 'shadow-2xl rounded-lg overflow-hidden'
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
                  src={containerPreviewUrl || `data:text/html;charset=utf-8,${encodeURIComponent(previewCode)}`}
                  className="w-full h-full border-0"
                  title="Preview"
                  onLoad={handleIframeLoad}
                  sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                />
              </div>
            </div>
          </div>
        ) : (
          // Code View with File Tree
          <div className={`h-full flex ${darkMode ? 'bg-[#1e1e1e]' : 'bg-gray-50'}`}>
            {/* Left Sidebar - File Tree */}
            <div className={`w-64 flex-shrink-0 border-r ${
              darkMode ? 'bg-[#252526] border-[#3e3e42]' : 'bg-gray-100 border-gray-300'
            }`}>
              {/* File Tree Header */}
              <div className={`px-3 py-2 border-b ${
                darkMode ? 'border-[#3e3e42]' : 'border-gray-300'
              }`}>
                <div className="flex items-center justify-between">
                  <span className={`text-xs font-semibold uppercase tracking-wide ${
                    darkMode ? 'text-[#858585]' : 'text-gray-500'
                  }`}>
                    Code Files
                  </span>
                  <button
                    onClick={onCopyCode}
                    className={`p-1 rounded hover:bg-opacity-10 ${
                      darkMode ? 'hover:bg-white' : 'hover:bg-black'
                    }`}
                    title="Copy All Code"
                  >
                    {copied ? (
                      <Check className={`w-3.5 h-3.5 ${darkMode ? 'text-green-400' : 'text-green-600'}`} />
                    ) : (
                      <Copy className={`w-3.5 h-3.5 ${darkMode ? 'text-[#858585]' : 'text-gray-500'}`} />
                    )}
                  </button>
                </div>
              </div>
              
              {/* File Tree */}
              <FileTree
                code={previewCode}
                darkMode={darkMode}
                onFileSelect={handleFileSelect}
                selectedFile={selectedFile}
              />
            </div>

            {/* Right Side - Code Editor */}
            <div className="flex-1 flex flex-col">
              {/* File Header */}
              <div className={`px-4 py-2 border-b flex items-center justify-between ${
                darkMode ? 'bg-[#1e1e1e] border-[#3e3e42]' : 'bg-white border-gray-300'
              }`}>
                <div className="flex items-center gap-2">
                  <Code className={`w-4 h-4 ${darkMode ? 'text-[#858585]' : 'text-gray-500'}`} />
                  <span className={`text-sm font-medium ${
                    darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                  }`}>
                    {selectedFile || 'Generated Code'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs ${
                    darkMode ? 'text-[#858585]' : 'text-gray-500'
                  }`}>
                    {(currentFileContent || previewCode).split('\n').length} lines
                  </span>
                  <button
                    onClick={onDownloadCode}
                    className={`p-1.5 rounded hover:bg-opacity-10 ${
                      darkMode ? 'hover:bg-white' : 'hover:bg-black'
                    }`}
                    title="Download"
                  >
                    <Download className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} />
                  </button>
                </div>
              </div>

              {/* Code Content */}
              <div className={`flex-1 overflow-auto custom-scrollbar ${
                darkMode ? 'bg-[#1e1e1e]' : 'bg-white'
              }`}>
                <div className="flex h-full">
                  {/* Line Numbers */}
                  <div className={`py-4 px-3 select-none ${
                    darkMode ? 'bg-[#1e1e1e] text-[#858585]' : 'bg-gray-50 text-gray-400'
                  }`}>
                    <pre className="text-xs font-mono leading-relaxed text-right">
                      {(currentFileContent || previewCode).split('\n').map((_, idx) => (
                        <div key={idx}>{idx + 1}</div>
                      ))}
                    </pre>
                  </div>
                  
                  {/* Code Content */}
                  <div className="flex-1 py-4 px-4 overflow-x-auto">
                    <pre className={`text-sm font-mono leading-relaxed ${
                      darkMode ? 'text-[#d4d4d4]' : 'text-gray-800'
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
    </div>
  );
};

export default CodePreview;
