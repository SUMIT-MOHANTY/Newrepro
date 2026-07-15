/**
 * PdfStreamViewer — Custom PDF viewer using react-pdf (PDF.js canvas renderer).
 * Does NOT use the browser's built-in PDF viewer (<iframe>, <embed>, <object>).
 * Renders each page to a <canvas> element, supporting:
 *   - Page-by-page navigation
 *   - Zoom in / out
 *   - Full-screen toggle
 *   - Chunked HTTP streaming (PDF.js range requests)
 */

import React, { useState, useCallback, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { useMemo } from 'react';

// Use a CDN worker source that matches the PDF.js version used by react-pdf
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

const ZOOM_STEP = 0.2;
const ZOOM_MIN  = 0.5;
const ZOOM_MAX  = 3.0;

export default function PdfStreamViewer({ url, filename = 'document.pdf' }) {
  const [numPages, setNumPages]   = useState(null);
  const [page, setPage]           = useState(1);
  const [scale, setScale]         = useState(1.2);
  const [fullscreen, setFullscreen] = useState(false);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const containerRef              = useRef(null);

  // Memoize options to prevent unnecessary reloads of the Document component
  const options = useMemo(() => ({
    rangeChunkSize: 65536,
    disableStream: false,
    disableAutoFetch: false,
  }), []);

  const onDocumentLoad = useCallback(({ numPages }) => {
    setNumPages(numPages);
    setLoading(false);
    setError(null);
  }, []);

  const onDocumentError = useCallback((err) => {
    console.error('[PdfStreamViewer] load error:', err);
    setError('Failed to load document. Please try again.');
    setLoading(false);
  }, []);

  const zoomIn  = () => setScale(s => Math.min(s + ZOOM_STEP, ZOOM_MAX));
  const zoomOut = () => setScale(s => Math.max(s - ZOOM_STEP, ZOOM_MIN));
  const resetZoom = () => setScale(1.2);

  const prevPage = () => setPage(p => Math.max(p - 1, 1));
  const nextPage = () => setPage(p => Math.min(p + 1, numPages || 1));

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen();
      setFullscreen(true);
    } else {
      document.exitFullscreen();
      setFullscreen(false);
    }
  };

  return (
    <div
      ref={containerRef}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: '#1a1a2e',
        borderRadius: fullscreen ? 0 : '12px',
        overflow: 'hidden',
        fontFamily: "'Inter', system-ui, sans-serif",
      }}
    >
      {/* ── Toolbar ── */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 16px',
        background: '#16213e',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
        flexShrink: 0,
        gap: 8,
      }}>
        {/* File name */}
        <span style={{ color: '#a0aec0', fontSize: 12, fontWeight: 600, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {filename}
        </span>

        {/* Page controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <ToolBtn onClick={prevPage} disabled={page <= 1} title="Previous page">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
          </ToolBtn>
          <span style={{ color: '#e2e8f0', fontSize: 12, minWidth: 70, textAlign: 'center' }}>
            {numPages ? `${page} / ${numPages}` : '—'}
          </span>
          <ToolBtn onClick={nextPage} disabled={!numPages || page >= numPages} title="Next page">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 18 15 12 9 6"/></svg>
          </ToolBtn>
        </div>

        {/* Zoom controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <ToolBtn onClick={zoomOut} disabled={scale <= ZOOM_MIN} title="Zoom out">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="8" y1="11" x2="14" y2="11"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          </ToolBtn>
          <button onClick={resetZoom} style={{ background: 'rgba(255,255,255,0.07)', border: 'none', borderRadius: 4, color: '#a0aec0', fontSize: 11, padding: '3px 8px', cursor: 'pointer', fontWeight: 600 }}>
            {Math.round(scale * 100)}%
          </button>
          <ToolBtn onClick={zoomIn} disabled={scale >= ZOOM_MAX} title="Zoom in">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          </ToolBtn>
        </div>

        {/* Fullscreen */}
        <ToolBtn onClick={toggleFullscreen} title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
          {fullscreen
            ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="10" y1="14" x2="3" y2="21"/><line x1="21" y1="3" x2="14" y2="10"/></svg>
            : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
          }
        </ToolBtn>
      </div>

      {/* ── Canvas area ── */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        overflowX: 'auto',
        display: 'flex',
        justifyContent: 'center',
        alignItems: loading || error ? 'center' : 'flex-start',
        padding: 16,
        background: '#1a1a2e',
      }}>
        {error ? (
          <div style={{ color: '#fc8181', textAlign: 'center', fontSize: 14 }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>⚠️</div>
            {error}
          </div>
        ) : loading ? (
          <LoadingSpinner />
        ) : null}

        <Document
          file={url}
          onLoadSuccess={onDocumentLoad}
          onLoadError={onDocumentError}
          loading={null}
          options={options}
        >
          <div style={{
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            borderRadius: 4,
            overflow: 'hidden',
            display: loading ? 'none' : 'block',
          }}>
            <Page
              pageNumber={page}
              scale={scale}
              renderTextLayer={true}
              renderAnnotationLayer={true}
              loading={<LoadingSpinner />}
              onRenderSuccess={() => setLoading(false)}
            />
          </div>
        </Document>
      </div>

      {/* ── Bottom page indicator strip ── */}
      {numPages && numPages > 1 && (
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          padding: '6px 0',
          background: '#16213e',
          borderTop: '1px solid rgba(255,255,255,0.06)',
          gap: 4,
          flexShrink: 0,
        }}>
          {Array.from({ length: Math.min(numPages, 20) }, (_, i) => i + 1).map(n => (
            <button
              key={n}
              onClick={() => setPage(n)}
              style={{
                width: n === page ? 20 : 8,
                height: 8,
                borderRadius: n === page ? 4 : '50%',
                border: 'none',
                background: n === page ? '#667eea' : 'rgba(255,255,255,0.2)',
                cursor: 'pointer',
                padding: 0,
                transition: 'all 0.2s',
              }}
            />
          ))}
          {numPages > 20 && <span style={{ color: '#718096', fontSize: 11 }}>…</span>}
        </div>
      )}
    </div>
  );
}

/* ── Small reusable toolbar button ── */
function ToolBtn({ onClick, disabled, title, children }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        background: disabled ? 'transparent' : 'rgba(255,255,255,0.07)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: 6,
        color: disabled ? '#4a5568' : '#a0aec0',
        padding: '5px 7px',
        cursor: disabled ? 'not-allowed' : 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'all 0.15s',
      }}
      onMouseEnter={e => !disabled && (e.currentTarget.style.background = 'rgba(255,255,255,0.12)')}
      onMouseLeave={e => !disabled && (e.currentTarget.style.background = 'rgba(255,255,255,0.07)')}
    >
      {children}
    </button>
  );
}

/* ── Loading spinner ── */
function LoadingSpinner() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: 32 }}>
      <div style={{
        width: 36,
        height: 36,
        border: '3px solid rgba(102,126,234,0.2)',
        borderTop: '3px solid #667eea',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <span style={{ color: '#718096', fontSize: 13 }}>Loading document…</span>
    </div>
  );
}
