import React, { useState } from 'react';

const FileCreationFeed = ({ logs }) => {
  const [selectedFile, setSelectedFile] = useState(null);

  // Filter logs to only file_created events
  const fileEvents = logs.filter(log => log.type === 'file_created');

  if (fileEvents.length === 0) {
    return null;
  }

  return (
    <div className="mt-4 border border-gray-700 rounded-lg bg-gray-900">
      <div className="px-4 py-3 border-b border-gray-700">
        <h3 className="text-sm font-semibold text-gray-200">
          📁 Files Created ({fileEvents.length})
        </h3>
      </div>
      
      <div className="p-4 max-h-96 overflow-y-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
          {fileEvents.map((event, idx) => (
            <button
              key={idx}
              onClick={() => setSelectedFile(event)}
              className="text-left px-3 py-2 rounded bg-gray-800 hover:bg-gray-700 transition-colors border border-gray-700 hover:border-blue-500"
            >
              <div className="flex items-center gap-2">
                <span className="text-blue-400">📄</span>
                <span className="text-sm text-gray-300 truncate">
                  {event.file_path}
                </span>
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {new Date(event.time).toLocaleTimeString()}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* File Content Modal */}
      {selectedFile && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4"
          onClick={() => setSelectedFile(null)}
        >
          <div 
            className="bg-gray-900 rounded-lg border border-gray-700 max-w-4xl w-full max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-blue-400">📄</span>
                <h3 className="text-sm font-semibold text-gray-200">
                  {selectedFile.file_path}
                </h3>
              </div>
              <button
                onClick={() => setSelectedFile(null)}
                className="text-gray-400 hover:text-gray-200 text-xl"
              >
                ×
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-4">
              <pre className="text-xs text-gray-300 font-mono bg-gray-950 p-4 rounded border border-gray-800 overflow-x-auto">
                {selectedFile.file_content}
              </pre>
            </div>

            {/* Footer */}
            <div className="px-4 py-3 border-t border-gray-700 flex justify-between items-center">
              <span className="text-xs text-gray-500">
                Created at {new Date(selectedFile.time).toLocaleString()}
              </span>
              <button
                onClick={() => setSelectedFile(null)}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FileCreationFeed;
