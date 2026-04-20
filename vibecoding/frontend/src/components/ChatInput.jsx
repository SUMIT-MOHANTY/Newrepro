import { useState, useRef } from 'react';
import { Send, Plus, MessageSquare, Code2, X, Image as ImageIcon } from 'lucide-react';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';

const ChatInput = ({ 
  input, 
  setInput, 
  onSend, 
  loading, 
  darkMode,
  disabled = false,
  discussMode = false,
  onToggleDiscuss,
  onImageUpload,
}) => {
  const [selectedImages, setSelectedImages] = useState([]);
  const fileInputRef = useRef(null);

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    const imageFiles = files.filter(file => file.type.startsWith('image/'));
    
    if (imageFiles.length > 0) {
      // Create preview URLs
      const newImages = imageFiles.map(file => ({
        file,
        preview: URL.createObjectURL(file),
        name: file.name
      }));
      
      setSelectedImages(prev => [...prev, ...newImages]);
    }
  };

  const handlePaste = (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    const imageFiles = [];
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) imageFiles.push(file);
      }
    }

    if (imageFiles.length > 0) {
      e.preventDefault();
      const newImages = imageFiles.map((file, i) => ({
        file,
        preview: URL.createObjectURL(file),
        name: file.name || `pasted-image-${Date.now()}-${i}.png`
      }));
      setSelectedImages(prev => [...prev, ...newImages]);
    }
  };

  const removeImage = (index) => {
    setSelectedImages(prev => {
      const newImages = [...prev];
      URL.revokeObjectURL(newImages[index].preview);
      newImages.splice(index, 1);
      return newImages;
    });
  };

  const fileToBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  const handleSend = async () => {
    if (!input.trim() && selectedImages.length === 0) return;

    let imageDataUrls = [];
    if (selectedImages.length > 0) {
      imageDataUrls = await Promise.all(
        selectedImages.map(img => fileToBase64(img.file))
      );
    }

    if (selectedImages.length > 0 && onImageUpload) {
      onImageUpload(selectedImages.map(img => img.file), input);
    }

    onSend(imageDataUrls);

    if (selectedImages.length > 0) {
      selectedImages.forEach(img => URL.revokeObjectURL(img.preview));
      setSelectedImages([]);
    }
  };

  return (
    <div className={cn(
      'p-4 border-t',
      darkMode ? 'border-white/10' : 'border-gray-200'
    )}>
      {/* Image Previews */}
      {selectedImages.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {selectedImages.map((image, index) => (
            <div 
              key={index}
              className={cn(
                'relative group rounded-lg overflow-hidden border',
                darkMode ? 'border-white/10' : 'border-gray-200'
              )}
            >
              <img 
                src={image.preview} 
                alt={image.name}
                className="w-20 h-20 object-cover"
              />
              <button
                onClick={() => removeImage(index)}
                className="absolute top-1 right-1 p-1 rounded-full bg-black/60 hover:bg-black/80 text-white opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X className="w-3 h-3" />
              </button>
              <div className={cn(
                'absolute bottom-0 left-0 right-0 px-1.5 py-0.5 text-[10px] truncate',
                'bg-black/60 text-white'
              )}>
                {image.name}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Input Area */}
      <div className="relative">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPaste={handlePaste}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={disabled ? "Select or create a project to start..." : discussMode ? "Ask anything, discuss ideas..." : "Describe your app..."}
          disabled={loading || disabled}
          rows="3"
          className={cn(
            'w-full px-4 py-3 pr-12 rounded-xl text-sm resize-none transition-colors focus:outline-none focus:ring-2 border max-h-24 overflow-y-auto',
            darkMode 
              ? 'bg-white/5 text-gray-200 placeholder-gray-500 border-white/10' 
              : 'bg-gray-50 text-gray-900 placeholder-gray-400 border-gray-200',
            discussMode
              ? 'focus:ring-blue-500/50'
              : 'focus:ring-purple-500/50',
            (loading || disabled) && 'opacity-50 cursor-not-allowed'
          )}
        />
        <Button
          onClick={handleSend}
          disabled={loading || (!input.trim() && selectedImages.length === 0) || disabled}
          size="icon"
          className={cn(
            'absolute right-3 bottom-3 w-8 h-8 rounded-lg transition-all',
            discussMode
              ? 'bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600'
              : darkMode
                ? 'bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700'
                : 'bg-blue-500 hover:bg-blue-600'
          )}
        >
          <Send className="w-4 h-4" />
        </Button>
      </div>

      {/* Bottom bar */}
      <div className={cn(
        'flex items-center justify-between mt-2 text-xs',
        darkMode ? 'text-gray-500' : 'text-gray-400'
      )}>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            onChange={handleFileSelect}
            className="hidden"
          />
          <Button 
            variant="ghost"
            size="sm"
            disabled={disabled}
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              'flex items-center gap-1.5 h-7 px-2.5 text-xs font-bold transition-all rounded-lg',
              darkMode 
                ? 'text-gray-400 hover:text-gray-200 hover:bg-white/5' 
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100',
              selectedImages.length > 0 && (darkMode ? 'text-purple-400 bg-purple-500/10' : 'text-purple-600 bg-purple-50')
            )}
          >
            {selectedImages.length > 0 ? (
              <>
                <ImageIcon className="w-4 h-4" />
                <span>{selectedImages.length} image{selectedImages.length > 1 ? 's' : ''}</span>
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                <span>Attach</span>
              </>
            )}
          </Button>

          {/* Discuss mode toggle */}
          <button
            onClick={onToggleDiscuss}
            disabled={disabled}
            title={discussMode ? 'Discuss mode enabled - Click to disable' : 'Discuss mode disabled - Click to enable'}
            className={cn(
              'flex items-center gap-1.5 h-7 px-3 rounded-full text-xs font-bold transition-all border shadow-sm',
              discussMode
                ? (darkMode ? 'bg-blue-600/20 border-blue-500/40 text-blue-400' : 'bg-blue-50 border-blue-200 text-blue-600')
                : (darkMode 
                    ? 'bg-white/5 border-white/10 text-gray-400 hover:text-gray-200 hover:bg-white/10' 
                    : 'bg-gray-50 border-gray-300 text-gray-600 hover:text-gray-900 hover:bg-gray-100'),
              disabled && 'opacity-40 cursor-not-allowed shadow-none'
            )}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            <span>Discuss</span>
          </button>
        </div>
        <span>{disabled ? 'Select a project first' : 'Press Enter to send'}</span>
      </div>
    </div>
  );
};

export default ChatInput;
