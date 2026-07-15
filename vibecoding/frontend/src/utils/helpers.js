export const formatCode = (code) => {
  if (!code) return '';
  
  try {
    let formatted = code;
    let indent = 0;
    const lines = formatted.split('\n');
    const formattedLines = lines.map(line => {
      const trimmed = line.trim();
      
      // Decrease indent for closing tags
      if (trimmed.startsWith('</') || trimmed.startsWith('}') || trimmed.startsWith(']')) {
        indent = Math.max(0, indent - 1);
      }
      
      const indentedLine = '  '.repeat(indent) + trimmed;
      
      // Increase indent for opening tags
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

export const downloadCode = (code, filename = 'app.html') => {
  const blob = new Blob([code], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

export const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (error) {
    console.error('Failed to copy to clipboard:', error);
    return false;
  }
};

export const getSuggestions = () => [
  "Add Dynamic Blog Section",
  "Add Responsive Contact Form", 
  "Implement Theme Toggle",
  "Create Navigation Menu",
  "Add Image Gallery",
  "Build Login Form",
  "Create Product Cards",
  "Add Footer Section"
];
