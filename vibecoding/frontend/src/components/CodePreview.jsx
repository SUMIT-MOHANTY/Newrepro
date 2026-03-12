import React, { useRef } from 'react';
import { Eye, Code, Copy, Check, RefreshCw, Download, Sparkles } from 'lucide-react';
import { Button } from './ui/button';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from './ui/select';
import { cn } from '@/lib/utils';

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
  onLoadVersion 
}) => {
  const iframeRef = useRef(null);

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
    <div className="flex-1 flex flex-col min-h-0" style={{ position: 'relative', overflow: 'visible' }}>
      {/* Tab Bar - Always Visible */}
      <div 
        className="flex items-center gap-2 px-6 py-3 border-b flex-shrink-0"
        style={{
          backgroundColor: darkMode ? '#252526' : '#f9fafb',
          borderColor: darkMode ? '#3e3e42' : '#e5e7eb',
          minHeight: '48px',
          flexShrink: 0,
          display: 'flex',
          visibility: 'visible',
          opacity: 1,
          position: 'sticky',
          top: 0,
          zIndex: 9999,
          width: '100%'
        }}
      >
        <Button
          onClick={() => setActiveTab('preview')}
          variant={activeTab === 'preview' ? 'default' : 'ghost'}
          size="sm"
          className={cn(
            'rounded-md text-sm h-9 px-4 py-2 flex items-center gap-2',
            activeTab === 'preview'
              ? 'bg-blue-600 text-white hover:bg-blue-700'
              : darkMode
                ? 'text-[#cccccc] hover:text-white hover:bg-[#2d2d30]'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          )}
          disabled={!previewCode}
          style={{
            opacity: !previewCode ? 0.5 : 1,
            cursor: !previewCode ? 'not-allowed' : 'pointer'
          }}
        >
          <Eye className="w-4 h-4 mr-2" />
          Preview
        </Button>
        <Button
          onClick={() => setActiveTab('code')}
          variant={activeTab === 'code' ? 'default' : 'ghost'}
          size="sm"
          className={cn(
            'rounded-md text-sm h-9 px-4 py-2 flex items-center gap-2',
            activeTab === 'code'
              ? 'bg-blue-600 text-white hover:bg-blue-700'
              : darkMode
                ? 'text-[#cccccc] hover:text-white hover:bg-[#2d2d30]'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          )}
          disabled={!previewCode}
          style={{
            opacity: !previewCode ? 0.5 : 1,
            cursor: !previewCode ? 'not-allowed' : 'pointer'
          }}
        >
          <Code className="w-4 h-4 mr-2" />
          Code
        </Button>
        
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
          </div>
          
          <div className="h-4 w-px bg-gray-300 dark:bg-gray-600" />
          
          {/* Action Buttons - Always visible but disabled when no code */}
          <Button
            onClick={onCopyCode}
            variant="ghost"
            size="icon"
            disabled={!previewCode}
            className={cn(
              'rounded-md',
              darkMode 
                ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
                : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
            )}
            title="Copy Code"
            style={{
              opacity: !previewCode ? 0.5 : 1,
              cursor: !previewCode ? 'not-allowed' : 'pointer'
            }}
          >
            {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
          </Button>
          <Button
            onClick={onRefreshPreview}
            variant="ghost"
            size="icon"
            disabled={!previewCode}
            className={cn(
              'rounded-md',
              darkMode 
                ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
                : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
            )}
            title="Refresh"
            style={{
              opacity: !previewCode ? 0.5 : 1,
              cursor: !previewCode ? 'not-allowed' : 'pointer'
            }}
          >
            <RefreshCw className="w-4 h-4" />
          </Button>
          <Button
            onClick={onDownloadCode}
            variant="ghost"
            size="icon"
            disabled={!previewCode}
            className={cn(
              'rounded-md',
              darkMode 
                ? 'hover:bg-[#2d2d30] text-[#cccccc] hover:text-white' 
                : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
            )}
            title="Download"
            style={{
              opacity: !previewCode ? 0.5 : 1,
              cursor: !previewCode ? 'not-allowed' : 'pointer'
            }}
          >
            <Download className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Preview/Code Area */}
      <div 
        className={`flex-1 min-h-0 flex flex-col overflow-auto`}
        style={{ flex: '1 1 auto', minHeight: 0 }}
      >
        {!previewCode ? (
          <div className="flex-1 min-h-0 flex items-center justify-center">
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
          <div className="flex-1 min-h-0 w-full">
            <iframe
              ref={iframeRef}
              srcDoc={previewCode}
              className="w-full h-full border-0"
              title="Preview"
              sandbox="allow-scripts allow-same-origin"
            />
          </div>
        ) : (
          <div className={`flex-1 min-h-0 overflow-auto custom-scrollbar ${
            darkMode ? 'bg-[#1e1e1e]' : 'bg-gray-50'
          }`}>
            <div className="p-6">
              {/* Code Header */}
              <div className={`flex items-center justify-between mb-4 pb-3 border-b ${
                darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
              }`}>
                <div className="flex items-center gap-2">
                  <Code className={`w-4 h-4 ${darkMode ? 'text-[#858585]' : 'text-gray-500'}`} />
                  <span className={`text-sm font-medium ${
                    darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                  }`}>Generated Code</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs ${
                    darkMode ? 'text-[#858585]' : 'text-gray-500'
                  }`}>{previewCode.split('\n').length} lines</span>
                  <button
                    onClick={onCopyCode}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                      darkMode 
                        ? 'bg-[#2d2d30] text-[#cccccc] hover:bg-[#3e3e42]' 
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {copied ? (
                      <span className="flex items-center gap-1">
                        <Check className="w-3 h-3" />
                        Copied
                      </span>
                    ) : (
                      <span className="flex items-center gap-1">
                        <Copy className="w-3 h-3" />
                        Copy
                      </span>
                    )}
                  </button>
                </div>
              </div>
              
              {/* Code Content with Line Numbers */}
              <div className={`rounded-lg overflow-hidden border ${
                darkMode ? 'bg-[#1e1e1e] border-[#3e3e42]' : 'bg-white border-gray-200'
              }`}>
                <div className="flex">
                  {/* Line Numbers */}
                  <div className={`py-4 px-3 select-none flex-shrink-0 overflow-y-auto ${
                    darkMode ? 'bg-[#252526] text-[#858585]' : 'bg-gray-50 text-gray-400'
                  }`}>
                    <pre className="text-xs font-mono leading-relaxed text-right whitespace-pre">
                      {formatCode(previewCode).split('\n').map((_, idx) => (
                        <div key={idx}>{idx + 1}</div>
                      ))}
                    </pre>
                  </div>
                  
                  {/* Code Content */}
                  <div className="flex-1 py-4 px-4 overflow-x-auto overflow-y-auto">
                    <pre className={`text-sm font-mono leading-relaxed whitespace-pre-wrap break-words ${
                      darkMode ? 'text-[#d4d4d4]' : 'text-gray-800'
                    }`}>
                      <code className="language-html">{formatCode(previewCode)}</code>
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
