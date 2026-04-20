import React, { useState } from 'react';
import { Palette, Type, Code, MessageSquare, Trash2, X } from 'lucide-react';

const EditElementMenu = ({ 
  element, 
  position, 
  onClose, 
  onEditProperties, 
  onEditCode, 
  onSendToAI,
  onDelete,
  darkMode 
}) => {
  const [showProperties, setShowProperties] = useState(false);

  if (!element) return null;

  const bg = darkMode ? '#2d2d30' : '#ffffff';
  const border = darkMode ? '#3e3e42' : '#e5e7eb';
  const text = darkMode ? '#cccccc' : '#374151';
  const textMuted = darkMode ? '#858585' : '#6b7280';
  const hoverBg = darkMode ? '#3e3e42' : '#f3f4f6';
  const inputBg = darkMode ? '#1e1e1e' : '#ffffff';

  const itemStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    width: '100%',
    padding: '6px 12px',
    border: 'none',
    background: 'transparent',
    color: text,
    fontSize: '13px',
    cursor: 'pointer',
    borderRadius: '4px',
    textAlign: 'left',
  };

  const handlePropertyChange = (property, value) => {
    onEditProperties?.(element, property, value);
  };

  const handleSendToAI = () => {
    const elementInfo = {
      tagName: element.tagName,
      className: element.className,
      id: element.id,
      textContent: element.textContent,
      styles: element.styles || {}
    };
    onSendToAI?.(elementInfo);
    onClose();
  };

  return (
    <>
      {/* Backdrop */}
      <div
        style={{ position: 'fixed', inset: 0, zIndex: 50 }}
        onClick={onClose}
      />

      {/* Menu */}
      <div
        style={{
          position: 'fixed',
          zIndex: 9999,
          left: `${position.x}px`,
          top: `${position.y}px`,
          background: bg,
          border: `1px solid ${border}`,
          borderRadius: '8px',
          boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
          minWidth: '200px',
          padding: '4px',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '6px 8px',
          borderBottom: `1px solid ${border}`,
          marginBottom: '4px',
        }}>
          <span style={{ fontSize: '12px', fontWeight: 600, color: text }}>
            Edit Element
          </span>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: textMuted, padding: '2px', borderRadius: '4px',
              display: 'flex', alignItems: 'center',
            }}
            onMouseEnter={e => e.currentTarget.style.background = hoverBg}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
          >
            <X size={14} />
          </button>
        </div>

        {/* Menu Items */}
        <div>
          {/* Properties */}
          <button
            style={itemStyle}
            onClick={() => setShowProperties(!showProperties)}
            onMouseEnter={e => e.currentTarget.style.background = hoverBg}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
          >
            <Palette size={16} />
            Properties
          </button>

          {/* Edit Text */}
          <button
            style={itemStyle}
            onClick={() => {
              const newText = prompt('Enter new text:', element.textContent);
              if (newText !== null) handlePropertyChange('textContent', newText);
            }}
            onMouseEnter={e => e.currentTarget.style.background = hoverBg}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
          >
            <Type size={16} />
            Edit Text
          </button>

          {/* Edit Code */}
          <button
            style={itemStyle}
            onClick={() => { onEditCode?.(element); onClose(); }}
            onMouseEnter={e => e.currentTarget.style.background = hoverBg}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
          >
            <Code size={16} />
            Edit Code
          </button>

          {/* Ask AI */}
          <button
            style={itemStyle}
            onClick={handleSendToAI}
            onMouseEnter={e => e.currentTarget.style.background = hoverBg}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
          >
            <MessageSquare size={16} />
            Ask AI
          </button>

          {/* Divider */}
          <div style={{ height: '1px', background: border, margin: '4px 0' }} />

          {/* Delete */}
          <button
            style={{ ...itemStyle, color: '#ef4444' }}
            onClick={() => {
              if (window.confirm('Delete this element?')) {
                onDelete?.(element);
                onClose();
              }
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(239,68,68,0.1)'}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
          >
            <Trash2 size={16} />
            Delete
          </button>
        </div>

        {/* Properties Panel */}
        {showProperties && (
          <div style={{
            marginTop: '8px',
            paddingTop: '8px',
            borderTop: `1px solid ${border}`,
            padding: '8px',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}>
            {/* Color */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label style={{ fontSize: '11px', color: textMuted, width: '64px' }}>Color:</label>
              <input
                type="color"
                defaultValue={element.styles?.color || '#000000'}
                onChange={(e) => handlePropertyChange('color', e.target.value)}
                style={{ width: '32px', height: '24px', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
              />
            </div>

            {/* Background */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label style={{ fontSize: '11px', color: textMuted, width: '64px' }}>BG Color:</label>
              <input
                type="color"
                defaultValue={element.styles?.backgroundColor || '#ffffff'}
                onChange={(e) => handlePropertyChange('backgroundColor', e.target.value)}
                style={{ width: '32px', height: '24px', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
              />
            </div>

            {/* Font Size */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label style={{ fontSize: '11px', color: textMuted, width: '64px' }}>Font Size:</label>
              <select
                defaultValue={element.styles?.fontSize || '16px'}
                onChange={(e) => handlePropertyChange('fontSize', e.target.value)}
                style={{
                  fontSize: '11px', padding: '2px 6px', borderRadius: '4px',
                  border: `1px solid ${border}`, background: inputBg, color: text,
                }}
              >
                {['10px','12px','14px','16px','18px','20px','24px','28px','32px','36px','48px'].map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>

            {/* Padding */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label style={{ fontSize: '11px', color: textMuted, width: '64px' }}>Padding:</label>
              <input
                type="text"
                defaultValue={element.styles?.padding || ''}
                onChange={(e) => handlePropertyChange('padding', e.target.value)}
                placeholder="e.g. 8px"
                style={{
                  fontSize: '11px', padding: '2px 6px', borderRadius: '4px', width: '70px',
                  border: `1px solid ${border}`, background: inputBg, color: text,
                }}
              />
            </div>
          </div>
        )}
      </div>
    </>
  );
};

export default EditElementMenu;
