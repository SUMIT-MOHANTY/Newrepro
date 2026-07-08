import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import PdfStreamViewer from '../components/PdfStreamViewer';
import {
    FileText,
    Download,
    Lock,
    AlertCircle,
    CheckCircle,
    Calendar,
    Eye,
    X,
    File,
    FileSpreadsheet,
    Presentation,
    Image,
    Globe,
    FileCode,
    Shield
} from 'lucide-react';
import { API_ENDPOINTS } from '../config';

const SharedDocumentViewer = () => {
    const { shareToken } = useParams();
    const navigate = useNavigate();

    // Recipient-specific view token passed as ?v_token=... in the share link
    const vToken = new URLSearchParams(window.location.search).get('v_token') || '';
    const sessionTimeoutRef = useRef(null);
    const devToolsCheckRef = useRef(null);

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [requirePassword, setRequirePassword] = useState(false);
    const [password, setPassword] = useState('');
    const [shareData, setShareData] = useState(null);
    const [verifying, setVerifying] = useState(false);
    const [selectedFile, setSelectedFile] = useState(null);
    const [viewerMode, setViewerMode] = useState('list'); // 'list' or 'viewer'
    const [fileContent, setFileContent] = useState('');
    const [loadingFile, setLoadingFile] = useState(false);
    const [sessionExpired, setSessionExpired] = useState(false);
    const [devToolsDetected, setDevToolsDetected] = useState(false);
    const [htmlCanvasUrl, setHtmlCanvasUrl] = useState('');
    const [officeViewerError, setOfficeViewerError] = useState(false);
    const [useGoogleViewer, setUseGoogleViewer] = useState(false);
    const [pendingPrint, setPendingPrint] = useState(false);
    const [generatingPdf, setGeneratingPdf] = useState(false);
    const iframeRef = useRef(null);

    // Security: Session timeout (30 minutes)
    const SESSION_TIMEOUT = 30 * 60 * 1000; // 30 minutes

    // Security: Disable text selection and context menu
    useEffect(() => {
        const disableSelection = (e) => {
            e.preventDefault();
            return false;
        };

        const disableContextMenu = (e) => {
            e.preventDefault();
            return false;
        };

        const disableKeyboardShortcuts = (e) => {
            // Disable common shortcuts for copying, saving, printing, etc.
            if (
                (e.ctrlKey || e.metaKey) &&
                (e.key === 'c' || e.key === 'a' || e.key === 's' || e.key === 'p' ||
                    e.key === 'u' || e.key === 'i' || e.key === 'j' || e.key === 'k' ||
                    e.key === 'h' || e.key === 'r' || e.key === 'f' || e.key === 'g')
            ) {
                e.preventDefault();
                return false;
            }

            // Disable F12, F11, Ctrl+Shift+I, Ctrl+Shift+J, Ctrl+U
            if (
                e.key === 'F12' || e.key === 'F11' ||
                ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'I' || e.key === 'J' || e.key === 'C')) ||
                ((e.ctrlKey || e.metaKey) && e.key === 'U')
            ) {
                e.preventDefault();
                return false;
            }
        };

        const disableDragAndDrop = (e) => {
            e.preventDefault();
            return false;
        };

        // Apply security measures
        document.addEventListener('selectstart', disableSelection);
        document.addEventListener('contextmenu', disableContextMenu);
        document.addEventListener('keydown', disableKeyboardShortcuts);
        document.addEventListener('dragstart', disableDragAndDrop);
        document.addEventListener('drop', disableDragAndDrop);

        // Disable image dragging
        const images = document.querySelectorAll('img');
        images.forEach(img => {
            img.addEventListener('dragstart', disableDragAndDrop);
        });

        return () => {
            document.removeEventListener('selectstart', disableSelection);
            document.removeEventListener('contextmenu', disableContextMenu);
            document.removeEventListener('keydown', disableKeyboardShortcuts);
            document.removeEventListener('dragstart', disableDragAndDrop);
            document.removeEventListener('drop', disableDragAndDrop);
        };
    }, []);

    // Security: DevTools detection
    useEffect(() => {
        const detectDevTools = () => {
            const threshold = 160;

            if (
                window.outerHeight - window.innerHeight > threshold ||
                window.outerWidth - window.innerWidth > threshold
            ) {
                setDevToolsDetected(true);
                return true;
            }

            // Additional detection methods
            let devtools = {
                open: false,
                orientation: null
            };

            // Use a different approach for devtools detection
            try {
                const element = document.createElement('div');
                Object.defineProperty(element, 'id', {
                    get: function () {
                        devtools.open = true;
                        return '';
                    }
                });

                console.log('%c', element);
                console.clear();

                if (devtools.open) {
                    setDevToolsDetected(true);
                    return true;
                }
            } catch (e) {
                // Fallback detection method
                const start = performance.now();
                // Simple timing check
                for (let i = 0; i < 100; i++) { }
                const end = performance.now();
                if (end - start > 50) { // Large delay indicates debugger/throttling
                    setDevToolsDetected(true);
                    return true;
                }
            }

            return false;
        };

        // Check every 2 seconds to avoid performance issues
        devToolsCheckRef.current = setInterval(() => {
            if (detectDevTools()) {
                clearInterval(devToolsCheckRef.current);
            }
        }, 2000);

        return () => {
            if (devToolsCheckRef.current) {
                clearInterval(devToolsCheckRef.current);
            }
        };
    }, []);

    // Security: Session timeout
    useEffect(() => {
        const resetTimeout = () => {
            if (sessionTimeoutRef.current) {
                clearTimeout(sessionTimeoutRef.current);
            }

            sessionTimeoutRef.current = setTimeout(() => {
                setSessionExpired(true);
            }, SESSION_TIMEOUT);
        };

        const handleActivity = () => {
            resetTimeout();
        };

        // Start timeout
        resetTimeout();

        // Reset timeout on user activity
        document.addEventListener('mousedown', handleActivity);
        document.addEventListener('mousemove', handleActivity);
        document.addEventListener('keypress', handleActivity);
        document.addEventListener('scroll', handleActivity);
        document.addEventListener('touchstart', handleActivity);

        return () => {
            if (sessionTimeoutRef.current) {
                clearTimeout(sessionTimeoutRef.current);
            }
            document.removeEventListener('mousedown', handleActivity);
            document.removeEventListener('mousemove', handleActivity);
            document.removeEventListener('keypress', handleActivity);
            document.removeEventListener('scroll', handleActivity);
            document.removeEventListener('touchstart', handleActivity);
        };
    }, []);

    // Security: Disable printing
    useEffect(() => {
        const style = document.createElement('style');
        style.innerHTML = `
            @media print {
                body * {
                    visibility: hidden !important;
                }
                body::before {
                    content: "Printing is not allowed for this document." !important;
                    visibility: visible !important;
                    position: absolute !important;
                    top: 50% !important;
                    left: 50% !important;
                    transform: translate(-50%, -50%) !important;
                    font-size: 24px !important;
                    color: #ef4444 !important;
                }
            }
        `;
        document.head.appendChild(style);

        return () => {
            document.head.removeChild(style);
        };
    }, []);

    const prepareIframeForPrinting = () => {
        try {
            const iframe = iframeRef.current;
            if (!iframe) return;
            const doc = iframe.contentDocument || iframe.contentWindow.document;
            if (!doc) return;

            // 1. Inject CSS for @media print first
            let style = doc.getElementById('dynamic-print-styles');
            if (!style) {
                style = doc.createElement('style');
                style.id = 'dynamic-print-styles';
                style.innerHTML = `
                    @media print {
                      @page {
                        size: A4 landscape;
                        margin: 0;
                      }
                      * {
                        -webkit-print-color-adjust: exact !important;
                        print-color-adjust: exact !important;
                      }
                      #nav, #pr, .no-print {
                        display: none !important;
                      }
                    }
                `;
                doc.head.appendChild(style);
            }

            // 2. Iteratively inspect all elements and override height:100vh and overflow:hidden
            const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_ELEMENT, null, false);
            let node;
            while (node = walker.nextNode()) {
                const computed = iframe.contentWindow.getComputedStyle(node);

                // If element has height: 100vh (or high vh), change it to auto
                if (computed.height.includes('vh') || computed.height === `${iframe.contentWindow.innerHeight}px`) {
                    node.style.setProperty('height', 'auto', 'important');
                    node.style.setProperty('min-height', '0', 'important');
                    node.style.setProperty('max-height', 'none', 'important');
                }

                // If element has overflow: hidden, override to overflow: visible or auto
                if (computed.overflow === 'hidden' || computed.overflowX === 'hidden' || computed.overflowY === 'hidden') {
                    node.style.setProperty('overflow', 'visible', 'important');
                    node.style.setProperty('overflow-x', 'visible', 'important');
                    node.style.setProperty('overflow-y', 'visible', 'important');
                }

                // For slides or absolute positioned pagination structures:
                if (node.classList.contains('slide')) {
                    node.style.setProperty('display', 'flex', 'important');
                    node.style.setProperty('position', 'relative', 'important');
                    node.style.setProperty('width', '100%', 'important');
                    node.style.setProperty('height', '100vh', 'important');
                    node.style.setProperty('page-break-after', 'always', 'important');
                    node.style.setProperty('break-after', 'page', 'important');
                    node.style.setProperty('overflow', 'hidden', 'important');
                    node.style.setProperty('box-sizing', 'border-box', 'important');
                }
            }

            // Also do body and html elements
            const htmlEl = doc.documentElement;
            const bodyEl = doc.body;

            htmlEl.style.setProperty('height', 'auto', 'important');
            htmlEl.style.setProperty('overflow', 'visible', 'important');

            bodyEl.style.setProperty('height', 'auto', 'important');
            bodyEl.style.setProperty('overflow', 'visible', 'important');

            const deckEl = doc.getElementById('deck');
            if (deckEl) {
                deckEl.style.setProperty('height', 'auto', 'important');
                deckEl.style.setProperty('width', '100%', 'important');
                deckEl.style.setProperty('position', 'relative', 'important');
                deckEl.style.setProperty('overflow', 'visible', 'important');
            }
        } catch (err) {
            console.error("Error preparing iframe for printing:", err);
        }
    };

    const handleIframeLoad = () => {
        if (pendingPrint && iframeRef.current) {
            setPendingPrint(false);
            setTimeout(() => {
                try {
                    prepareIframeForPrinting();
                    iframeRef.current.contentWindow.focus();
                    iframeRef.current.contentWindow.print();
                } catch (err) {
                    console.error("Print preview failed on load:", err);
                }
            }, 500);
        }
    };

    useEffect(() => {
        loadShareData();
    }, [shareToken]);

    const loadShareData = async (pwd = null) => {
        setLoading(true);
        setError('');

        try {
            const url = pwd
                ? `${API_ENDPOINTS.SHARED_DOCUMENT(shareToken)}?password=${encodeURIComponent(pwd)}`
                : API_ENDPOINTS.SHARED_DOCUMENT(shareToken);

            const response = await fetch(url);
            const data = await response.json();

            if (!response.ok) {
                if (response.status === 403) {
                    setError('Invalid password. Please try again.');
                    setRequirePassword(true);
                } else if (response.status === 404) {
                    setError('This share link is not found or has expired.');
                } else {
                    setError(data.detail || 'Failed to load shared documents.');
                }
                setLoading(false);
                return;
            }

            if (data.require_password) {
                setRequirePassword(true);
                setLoading(false);
                return;
            }

            setShareData(data);
            setRequirePassword(false);
            setLoading(false);
        } catch (err) {
            console.error('Error loading share:', err);
            setError('Failed to load shared documents. Please try again.');
            setLoading(false);
        }
    };

    const handlePasswordSubmit = async (e) => {
        e.preventDefault();
        if (!password.trim()) {
            setError('Please enter a password');
            return;
        }

        setVerifying(true);
        await loadShareData(password);
        setVerifying(false);
    };

    const handleViewFile = async (file) => {
        setSelectedFile(file);
        setViewerMode('viewer');
        // PdfStreamViewer fetches the stream URL itself — no pre-fetch needed.
        // The backend converts all file types to PDF on the fly.
        setLoadingFile(false);
        setFileContent('');
        setHtmlCanvasUrl('');
        setOfficeViewerError(false);
        setUseGoogleViewer(false);
    };

    const _handleViewFile_unused = async (file) => {
        // Kept for reference only — dead code, not called.
        try {
            const url = password
                ? `${API_ENDPOINTS.SHARED_DOCUMENT_VIEW(shareToken, file.id)}?password=${encodeURIComponent(password)}`
                : API_ENDPOINTS.SHARED_DOCUMENT_VIEW(shareToken, file.id);

            const response = await fetch(url);

            if (!response.ok) {
                throw new Error('Failed to load file');
            }

            // Check if it's a viewable content type
            const contentType = response.headers.get('content-type');

            if (contentType?.includes('text/html')) {
                const htmlContent = await response.text();

                // For HTML files, we'll use iframe with srcdoc for proper rendering
                // Canvas rendering for HTML is complex and may not preserve interactivity
                setFileContent(htmlContent);

            } else if (contentType?.includes('text/plain')) {
                const textContent = await response.text();
                setFileContent(`
                    <div style="user-select: none; -webkit-user-select: none; -moz-user-select: none; -ms-user-select: none;">
                        <pre style="white-space: pre-wrap; font-family: monospace; padding: 20px; line-height: 1.5; user-select: none;">${textContent}</pre>
                    </div>
                `);
            } else if (contentType?.startsWith('image/')) {
                // For images, use canvas rendering to prevent direct access
                const blob = await response.blob();
                const imageUrl = URL.createObjectURL(blob);

                // Create canvas-based image viewer
                const img = document.createElement('img');

                img.onload = () => {
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');

                    canvas.width = img.width;
                    canvas.height = img.height;
                    ctx.drawImage(img, 0, 0);

                    // Convert canvas to base64 and display
                    const canvasDataUrl = canvas.toDataURL();
                    setFileContent(`
                        <div style="display: flex; justify-content: center; align-items: center; min-height: 400px; padding: 20px; background: #f9fafb; user-select: none;">
                            <img src="${canvasDataUrl}" 
                                 style="max-width: 100%; max-height: 80vh; object-fit: contain; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); user-select: none; -webkit-user-drag: none; -webkit-touch-callout: none; pointer-events: none;" 
                                 alt="${file.filename}"
                                 oncontextmenu="return false;"
                                 ondragstart="return false;"
                                 onselectstart="return false;" />
                        </div>
                    `);
                    URL.revokeObjectURL(imageUrl);
                };

                img.onerror = () => {
                    URL.revokeObjectURL(imageUrl);
                    setFileContent(`
                        <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 400px; padding: 40px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; text-align: center; user-select: none;">
                            <h3 style="color: #ef4444; margin: 0 0 10px 0; font-size: 18px; user-select: none;">Error loading image</h3>
                            <p style="color: #6b7280; margin: 0; font-size: 14px; user-select: none;">Failed to load image content.</p>
                        </div>
                    `);
                };

                img.src = imageUrl;
            } else {
                // For other file types, show a message
                setFileContent(`
                    <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 400px; padding: 40px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; text-align: center; user-select: none;">
                        <div style="background: #f3f4f6; border-radius: 50%; width: 80px; height: 80px; display: flex; align-items: center; justify-content: center; margin-bottom: 20px;">
                            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#6b7280" stroke-width="2">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                                <polyline points="14,2 14,8 20,8"></polyline>
                            </svg>
                        </div>
                        <h3 style="color: #374151; margin: 0 0 10px 0; font-size: 18px; user-select: none;">Preview not available</h3>
                        <p style="color: #6b7280; margin: 0; font-size: 14px; user-select: none;">This file type cannot be previewed online.</p>
                        ${shareData?.can_download ? '<p style="color: #6b7280; margin: 10px 0 0 0; font-size: 14px; user-select: none;">You can download the file to view it.</p>' : ''}
                    </div>
                `);
            }
        } catch (err) {
            console.error('Error loading file:', err);
            setFileContent(`
                <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 400px; padding: 40px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; text-align: center; user-select: none;">
                    <div style="background: #fef2f2; border-radius: 50%; width: 80px; height: 80px; display: flex; align-items: center; justify-content: center; margin-bottom: 20px;">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="15" y1="9" x2="9" y2="15"></line>
                            <line x1="9" y1="9" x2="15" y2="15"></line>
                        </svg>
                    </div>
                    <h3 style="color: #ef4444; margin: 0 0 10px 0; font-size: 18px; user-select: none;">Error loading file</h3>
                    <p style="color: #6b7280; margin: 0; font-size: 14px; user-select: none;">Failed to load file content. Please try again.</p>
                </div>
            `);
        } finally {
            setLoadingFile(false);
        }
    };

    const handleDownload = async (fileId, filename) => {
        if (!shareData?.can_download) {
            alert('Downloads are not allowed for this share.');
            return;
        }

        const ext = filename.split('.').pop().toLowerCase();
        const isHtml = ext === 'html' || ext === 'htm';

        if (isHtml) {
            setGeneratingPdf(true);

            try {
                const params = new URLSearchParams();
                if (password) params.append('password', encodeURIComponent(password));
                if (vToken) params.append('v_token', vToken);
                const r = new URLSearchParams(window.location.search).get('r');
                if (r) params.append('r', r);

                const base = API_ENDPOINTS.SHARED_DOCUMENT_VIEW(shareToken, fileId);
                const streamUrl = params.toString() ? `${base}?${params.toString()}` : base;

                const response = await fetch(streamUrl);
                if (!response.ok) {
                    throw new Error('Failed to fetch document content');
                }
                const htmlText = await response.text();

                // Open a beautiful new popup window (not a tab)
                const width = 1200;
                const height = 900;
                const left = (window.screen.width - width) / 2;
                const top = (window.screen.height - height) / 2;

                const printWindow = window.open(
                    '',
                    '_blank',
                    `width=${width},height=${height},left=${left},top=${top},toolbar=no,menubar=no,scrollbars=yes,status=no`
                );

                if (!printWindow) {
                    alert("Pop-up blocked! Please allow pop-ups for this site to download the document.");
                    setGeneratingPdf(false);
                    return;
                }

                // Parse the original HTML
                const parser = new DOMParser();
                const doc = parser.parseFromString(htmlText, 'text/html');

                // Determine page size and layout properties dynamically based on target appearance
                let pageSize = 'portrait';
                let pageMargin = '0.5in'; // Use clean document margins for standard portrait reports

                // 1. Detect if the original HTML explicitly mandates standard page settings
                if (/size\s*:\s*landscape/i.test(htmlText)) {
                    pageSize = 'landscape';
                    pageMargin = '0';
                } else if (/size\s*:\s*portrait/i.test(htmlText)) {
                    pageSize = 'portrait';
                    pageMargin = '0.5in';
                } else {
                    // 2. Fallback to heuristic: if it structures slides or a slide-deck viewport container, default to landscape
                    const hasSlides = doc.getElementsByClassName('slide').length > 0 || 
                                      doc.querySelector('#deck') !== null ||
                                      /class=["']slide["']/i.test(htmlText);
                    if (hasSlides) {
                        pageSize = 'landscape';
                        pageMargin = '0'; // Slide decks look perfect edge-to-edge
                    }
                }

                // Create the beautiful overlay HTML structure
                const overlayHtml = `
                    <div id="print-instructions-overlay">
                        <div class="spinner"></div>
                        <div class="title">Preparing PDF Download...</div>
                        <div class="subtitle">Please select <b>"Save as PDF"</b> as the Destination in the print dialog. This window will close automatically after saving.</div>
                    </div>
                `;

                // Insert the custom high-end styles in doc.head
                const printStyle = doc.createElement('style');
                printStyle.innerHTML = `
                    /* Screen Styles: Beautiful Instructions Overlay */
                    @media screen {
                        #print-instructions-overlay {
                            position: fixed;
                            inset: 0;
                            background: #ffffff;
                            z-index: 999999;
                            display: flex;
                            flex-direction: column;
                            align-items: center;
                            justify-content: center;
                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                            color: #0f172a;
                            text-align: center;
                            padding: 20px;
                        }
                        .spinner {
                            width: 50px;
                            height: 50px;
                            border: 4px solid #e2e8f0;
                            border-top-color: #6366f1;
                            border-radius: 50%;
                            animation: spin 1s linear infinite;
                            margin-bottom: 24px;
                        }
                        @keyframes spin {
                            to { transform: rotate(360deg); }
                        }
                        .title {
                            font-size: 22px;
                            font-weight: 600;
                            margin-bottom: 8px;
                            color: #0f172a;
                        }
                        .subtitle {
                            font-size: 14px;
                            color: #64748b;
                            max-width: 420px;
                            line-height: 1.6;
                        }
                    }

                    /* Print Styles: Pixel-Perfect Page Splits */
                    @media print {
                        @page {
                            size: ${pageSize};
                            margin: ${pageMargin};
                        }
                        #print-instructions-overlay {
                            display: none !important;
                        }
                        body, html {
                            height: auto !important;
                            overflow: visible !important;
                            margin: 0 !important;
                            padding: 0 !important;
                            -webkit-print-color-adjust: exact !important;
                            print-color-adjust: exact !important;
                            background: white !important;
                        }
                        #deck {
                            height: auto !important;
                            width: 100% !important;
                            overflow: visible !important;
                            position: relative !important;
                            background: transparent !important;
                        }
                        .slide {
                            display: flex !important; /* Force display all slides */
                            position: relative !important; /* Force relative positioning for printing flow */
                            page-break-after: always !important;
                            break-after: page !important;
                            width: 100% !important;
                            height: 100vh !important; /* Match page height exactly */
                            margin: 0 !important;
                            padding: 38px 58px 50px 72px !important;
                            box-sizing: border-box !important;
                            overflow: hidden !important;
                        }
                    }
                `;
                doc.head.appendChild(printStyle);

                // Prepend overlay inside body
                const tempDiv = doc.createElement('div');
                tempDiv.innerHTML = overlayHtml.trim();
                doc.body.insertBefore(tempDiv.firstChild, doc.body.firstChild);

                // Add print and auto-close trigger script at the bottom of the body
                const scriptEl = doc.createElement('script');
                scriptEl.innerHTML = `
                    window.addEventListener('DOMContentLoaded', () => {
                        // Give assets, fonts, and layout a short moment to compile perfectly
                        setTimeout(() => {
                            window.print();
                            window.close();
                        }, 800);
                    });
                `;
                doc.body.appendChild(scriptEl);

                // Write the full parsed document to the popup window
                printWindow.document.open();
                printWindow.document.write(doc.documentElement.outerHTML);
                printWindow.document.close();

                // Stop the local loading screen spinner
                setGeneratingPdf(false);

            } catch (err) {
                console.error("Error setting up print download:", err);
                setGeneratingPdf(false);
                alert("Failed to initialize download. Please try again.");
            }
            return;
        }

        // Non-HTML files (like PDFs, docx, etc.):
        try {
            const params = new URLSearchParams();
            if (password) params.append('password', encodeURIComponent(password));
            if (vToken) params.append('v_token', vToken);
            const r = new URLSearchParams(window.location.search).get('r');
            if (r) params.append('r', r);

            const base = API_ENDPOINTS.SHARED_DOCUMENT_DOWNLOAD(shareToken, fileId);
            const url = params.toString() ? `${base}?${params.toString()}` : base;

            const response = await fetch(url);

            if (!response.ok) {
                throw new Error('Download failed');
            }

            const blob = await response.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;

            const stem = filename.replace(/\.[^/.]+$/, '');
            const isPdf = ext === 'pdf';
            const downloadExt = isPdf ? 'pdf' : 'pdf'; // Converted files are PDFs

            a.download = `${stem}.${downloadExt}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(downloadUrl);
            document.body.removeChild(a);
        } catch (err) {
            console.error('Download error:', err);
            alert('Failed to download file. Please try again.');
        }
    };

    const formatFileSize = (bytes) => {
        if (!bytes) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    };

    const formatDate = (dateString) => {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    const getFileIcon = (filename) => {
        const ext = filename.split('.').pop()?.toLowerCase();

        // Document files
        if (['pdf'].includes(ext)) return FileText;
        if (['doc', 'docx'].includes(ext)) return FileText;
        if (['txt', 'md', 'rtf'].includes(ext)) return FileCode;

        // Spreadsheet files
        if (['xlsx', 'xls', 'csv'].includes(ext)) return FileSpreadsheet;

        // Presentation files
        if (['pptx', 'ppt'].includes(ext)) return Presentation;

        // Web files
        if (['html', 'htm'].includes(ext)) return Globe;

        // Image files
        if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) return Image;

        // Default file icon
        return File;
    };

    const getFileIconColor = (filename) => {
        const ext = filename.split('.').pop()?.toLowerCase();

        // Document files - blue
        if (['pdf', 'doc', 'docx'].includes(ext)) return 'text-blue-500';

        // Text files - gray
        if (['txt', 'md', 'rtf'].includes(ext)) return 'text-gray-500';

        // Spreadsheet files - green
        if (['xlsx', 'xls', 'csv'].includes(ext)) return 'text-green-500';

        // Presentation files - orange
        if (['pptx', 'ppt'].includes(ext)) return 'text-orange-500';

        // Web files - purple
        if (['html', 'htm'].includes(ext)) return 'text-purple-500';

        // Image files - pink
        if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) return 'text-pink-500';

        // Default - gray
        return 'text-gray-400';
    };

    const isViewableFile = (filename) => {
        const ext = filename.split('.').pop()?.toLowerCase();
        return [
            'pdf', 'txt', 'md', 'html', 'htm', 'doc', 'docx',
            'xlsx', 'xls', 'pptx', 'ppt', 'csv',
            'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'
        ].includes(ext);
    };

    const isMicrosoftOfficeFile = (filename) => {
        const ext = filename.split('.').pop()?.toLowerCase();
        return ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(ext);
    };

    const getMicrosoftViewerUrl = (fileUrl) => {
        // Microsoft Office Online Viewer
        return `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(fileUrl)}`;
    };

    if (sessionExpired) {
        return (
            <div className="min-h-screen bg-app-bg-page flex items-center justify-center p-4">
                <div className="w-full max-w-md">
                    <div className="bg-app-bg-card rounded-2xl shadow-2xl border border-app-border p-8 text-center">
                        <div className="w-16 h-16 bg-orange-500/10 rounded-full flex items-center justify-center mx-auto mb-6">
                            <AlertCircle className="w-8 h-8 text-orange-400" />
                        </div>

                        <h1 className="text-2xl font-bold text-app-text-main mb-2">
                            Session Expired
                        </h1>
                        <p className="text-sm text-app-text-muted mb-6">
                            Your viewing session has expired for security reasons. Please refresh to continue.
                        </p>

                        <button
                            onClick={() => window.location.reload()}
                            className="px-6 py-3 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium"
                        >
                            Refresh Page
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    if (devToolsDetected) {
        return (
            <div className="min-h-screen bg-app-bg-page flex items-center justify-center p-4">
                <div className="w-full max-w-md">
                    <div className="bg-app-bg-card rounded-2xl shadow-2xl border border-red-500/20 p-8 text-center">
                        <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mx-auto mb-6">
                            <Shield className="w-8 h-8 text-red-400" />
                        </div>

                        <h1 className="text-2xl font-bold text-app-text-main mb-2">
                            Security Alert
                        </h1>
                        <p className="text-sm text-app-text-muted mb-6">
                            Developer tools have been detected. Access has been restricted for security reasons.
                        </p>

                        <button
                            onClick={() => navigate('/')}
                            className="px-6 py-3 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors font-medium"
                        >
                            Exit Viewer
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="min-h-screen bg-app-bg-page flex items-center justify-center">
                <div className="text-center">
                    <div className="w-16 h-16 border-4 border-app-primary border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
                    <p className="text-app-text-muted">Loading shared documents...</p>
                </div>
            </div>
        );
    }

    if (requirePassword && !shareData) {
        return (
            <div className="min-h-screen bg-app-bg-page flex items-center justify-center p-4">
                <div className="w-full max-w-md">
                    <div className="bg-app-bg-card rounded-2xl shadow-2xl border border-app-border p-8">
                        <div className="w-16 h-16 bg-app-primary/10 rounded-full flex items-center justify-center mx-auto mb-6">
                            <Lock className="w-8 h-8 text-app-primary" />
                        </div>

                        <h1 className="text-2xl font-bold text-app-text-main text-center mb-2">
                            Password Required
                        </h1>
                        <p className="text-sm text-app-text-muted text-center mb-6">
                            This share is password protected. Please enter the password to continue.
                        </p>

                        {error && (
                            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg flex items-start space-x-2">
                                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                                <p className="text-sm text-red-400">{error}</p>
                            </div>
                        )}

                        <form onSubmit={handlePasswordSubmit} className="space-y-4">
                            <div>
                                <input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="Enter password"
                                    className="w-full px-4 py-3 bg-app-bg-page border border-app-border rounded-lg text-app-text-main placeholder-app-text-muted focus:outline-none focus:ring-2 focus:ring-app-primary focus:border-app-primary"
                                    autoFocus
                                />
                            </div>

                            <button
                                type="submit"
                                disabled={verifying}
                                className="w-full px-6 py-3 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {verifying ? 'Verifying...' : 'Access Documents'}
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        );
    }

    if (error && !shareData) {
        return (
            <div className="min-h-screen bg-app-bg-page flex items-center justify-center p-4">
                <div className="w-full max-w-md">
                    <div className="bg-app-bg-card rounded-2xl shadow-2xl border border-app-border p-8 text-center">
                        <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mx-auto mb-6">
                            <AlertCircle className="w-8 h-8 text-red-400" />
                        </div>

                        <h1 className="text-2xl font-bold text-app-text-main mb-2">
                            Unable to Access
                        </h1>
                        <p className="text-sm text-app-text-muted mb-6">
                            {error}
                        </p>

                        <button
                            onClick={() => navigate('/')}
                            className="px-6 py-3 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium"
                        >
                            Go to Home
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    if (viewerMode === 'viewer' && selectedFile) {
        return (
            <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }} className="bg-app-bg-page">
                {/* Compact Viewer Header */}
                <div className="bg-app-bg-card border-b border-app-border flex-shrink-0">
                    <div className="max-w-7xl mx-auto px-4 py-2">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center space-x-3 min-w-0 flex-1">
                                <button
                                    onClick={() => setViewerMode('list')}
                                    className="p-1.5 text-app-text-muted hover:text-app-text-main hover:bg-app-bg-hover rounded-lg transition-colors flex-shrink-0"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                                <div className="min-w-0 flex-1">
                                    <h1 className="text-sm font-semibold text-app-text-main flex items-center space-x-2 truncate">
                                        {(() => {
                                            const IconComponent = getFileIcon(selectedFile.filename);
                                            const iconColor = getFileIconColor(selectedFile.filename);
                                            return <IconComponent className={`w-4 h-4 ${iconColor} flex-shrink-0`} />;
                                        })()}
                                        <span className="truncate">{selectedFile.filename}</span>
                                    </h1>
                                    <p className="text-xs text-app-text-muted truncate">
                                        {formatFileSize(selectedFile.size)} • {formatDate(selectedFile.uploaded_at)}
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-center space-x-2 flex-shrink-0 ml-4">
                                {shareData?.can_download && (
                                    <button
                                        onClick={() => handleDownload(selectedFile.id, selectedFile.filename)}
                                        className="px-3 py-1.5 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium flex items-center space-x-1.5 text-sm"
                                    >
                                        <Download className="w-3.5 h-3.5" />
                                        <span>Download</span>
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>
                </div>

                {/* Viewer Content with Scroll - Takes remaining viewport height */}
                <div style={{ flex: 1, overflow: 'hidden', userSelect: 'none', WebkitUserSelect: 'none', display: 'flex', flexDirection: 'column' }} className="bg-white">
                    {loadingFile ? (
                        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <div className="text-center">
                                <div className="w-12 h-12 border-4 border-app-primary border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
                                <p className="text-app-text-muted">Loading file...</p>
                            </div>
                        </div>
                    ) : (
                        <div style={{ flex: 1, overflow: 'hidden', position: 'relative', height: '100%' }}>
                            {generatingPdf && (
                                <div className="fixed inset-0 bg-white z-[99999] flex flex-col items-center justify-center">
                                    <div className="w-12 h-12 border-4 border-app-primary border-t-transparent rounded-full animate-spin mb-4"></div>
                                    <p className="text-app-text-main font-semibold text-base">Generating PDF for download...</p>
                                    <p className="text-app-text-muted text-xs mt-1">Please wait, this will download automatically when finished.</p>
                                </div>
                            )}
                            {selectedFile && (() => {
                                const params = new URLSearchParams();
                                if (password) params.append('password', encodeURIComponent(password));
                                if (vToken) params.append('v_token', vToken);
                                const r = new URLSearchParams(window.location.search).get('r');
                                if (r) params.append('r', r);
                                const base = API_ENDPOINTS.SHARED_DOCUMENT_VIEW(shareToken, selectedFile.id);
                                const streamUrl = params.toString() ? `${base}?${params.toString()}` : base;

                                const isHtml = selectedFile.filename.toLowerCase().endsWith('.html') || selectedFile.filename.toLowerCase().endsWith('.htm');

                                return (
                                    <div style={{ height: '100%' }}>
                                        {isHtml ? (
                                            <iframe
                                                ref={iframeRef}
                                                src={streamUrl}
                                                style={{ width: '100%', height: '100%', border: 'none', background: 'white' }}
                                                title={selectedFile.filename}
                                                sandbox="allow-scripts allow-same-origin allow-modals"
                                                onLoad={handleIframeLoad}
                                            />
                                        ) : (
                                            <PdfStreamViewer
                                                url={streamUrl}
                                                filename={selectedFile.filename}
                                            />
                                        )}
                                    </div>
                                );
                            })()}
                        </div>

                    )}
                </div>
            </div>
        );
    }

    return (
        <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', userSelect: 'none', WebkitUserSelect: 'none' }} className="bg-app-bg-page">
            {/* Compact Header */}
            <div className="bg-app-bg-card border-b border-app-border flex-shrink-0">
                <div className="max-w-6xl mx-auto px-4 py-3">
                    <div className="flex items-center justify-between">
                        <div className="min-w-0 flex-1">
                            <h1 className="text-lg font-bold text-app-text-main mb-0.5 truncate">
                                {shareData?.title || 'Shared Documents'}
                            </h1>
                            <div className="flex items-center space-x-3 text-xs text-app-text-muted flex-wrap">
                                <div className="flex items-center space-x-1">
                                    <Calendar className="w-3.5 h-3.5" />
                                    <span>Shared {formatDate(shareData?.created_at)}</span>
                                </div>
                                {shareData?.access_type === 'once' && (
                                    <div className="flex items-center space-x-1 text-yellow-400">
                                        <Eye className="w-3.5 h-3.5" />
                                        <span>One-time access</span>
                                    </div>
                                )}
                                {!shareData?.can_download && (
                                    <div className="flex items-center space-x-1 text-orange-400">
                                        <Lock className="w-3.5 h-3.5" />
                                        <span>View only</span>
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="flex items-center space-x-2 flex-shrink-0 ml-4">
                            <div className="px-3 py-1.5 bg-green-500/10 border border-green-500/20 rounded-lg">
                                <div className="flex items-center space-x-1.5">
                                    <CheckCircle className="w-4 h-4 text-green-400" />
                                    <span className="text-xs font-medium text-green-400">
                                        {shareData?.files?.length || 0} Document{shareData?.files?.length !== 1 ? 's' : ''}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Content with Scroll - Takes remaining viewport height */}
            <div style={{ flex: 1, overflow: 'auto' }}>
                <div className="max-w-6xl mx-auto px-4 py-6">
                    {shareData?.access_type === 'once' && (
                        <div className="mb-6 p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-xl">
                            <div className="flex items-start space-x-3">
                                <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                                <div>
                                    <p className="text-sm font-medium text-yellow-400 mb-1">
                                        One-Time Access Link
                                    </p>
                                    <p className="text-sm text-yellow-400/80">
                                        This link can only be accessed once. Make sure to download all documents you need before leaving this page.
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}

                    {!shareData?.can_download && (
                        <div className="mb-6 p-4 bg-orange-500/10 border border-orange-500/20 rounded-xl">
                            <div className="flex items-start space-x-3">
                                <Lock className="w-5 h-5 text-orange-400 flex-shrink-0 mt-0.5" />
                                <div>
                                    <p className="text-sm font-medium text-orange-400 mb-1">
                                        View Only Mode
                                    </p>
                                    <p className="text-sm text-orange-400/80">
                                        Downloads are disabled for this share. You can only view the documents online.
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}

                    <div className="bg-app-bg-card rounded-2xl shadow-lg border border-app-border overflow-hidden">
                        <div className="p-6 border-b border-app-border">
                            <h2 className="text-lg font-bold text-app-text-main">Documents</h2>
                        </div>

                        <div className="divide-y divide-app-border">
                            {shareData?.files?.map((file) => (
                                <div
                                    key={file.id}
                                    className="p-6 hover:bg-app-bg-hover transition-colors"
                                    style={{ userSelect: 'none', WebkitUserSelect: 'none' }}
                                    onContextMenu={(e) => e.preventDefault()}
                                    onDragStart={(e) => e.preventDefault()}
                                >
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center space-x-4 flex-1 min-w-0">
                                            <div className="w-12 h-12 bg-app-primary/10 rounded-lg flex items-center justify-center flex-shrink-0">
                                                {(() => {
                                                    const IconComponent = getFileIcon(file.filename);
                                                    const iconColor = getFileIconColor(file.filename);
                                                    return <IconComponent className={`w-6 h-6 ${iconColor}`} />;
                                                })()}
                                            </div>

                                            <div className="flex-1 min-w-0">
                                                <h3 className="text-base font-semibold text-app-text-main truncate mb-1">
                                                    {file.filename}
                                                </h3>
                                                <div className="flex items-center space-x-3 text-sm text-app-text-muted">
                                                    <span>{formatFileSize(file.size)}</span>
                                                    {file.type && (
                                                        <>
                                                            <span>•</span>
                                                            <span>{file.type}</span>
                                                        </>
                                                    )}
                                                    {file.uploaded_at && (
                                                        <>
                                                            <span>•</span>
                                                            <span>{formatDate(file.uploaded_at)}</span>
                                                        </>
                                                    )}
                                                </div>
                                            </div>
                                        </div>

                                        <div className="flex items-center space-x-2 ml-4">
                                            {isViewableFile(file.filename) && (
                                                <button
                                                    onClick={() => handleViewFile(file)}
                                                    className="px-4 py-2 border border-app-border text-app-text-main rounded-lg hover:bg-app-bg-hover transition-colors font-medium flex items-center space-x-2"
                                                >
                                                    <Eye className="w-4 h-4" />
                                                    <span>View</span>
                                                </button>
                                            )}

                                            {shareData?.can_download && (
                                                <button
                                                    onClick={() => handleDownload(file.id, file.filename)}
                                                    className="px-4 py-2 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium flex items-center space-x-2"
                                                >
                                                    <Download className="w-4 h-4" />
                                                    <span>Download</span>
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="mt-8 text-center pb-4">
                        <p className="text-sm text-app-text-muted">
                            Powered by <span className="font-semibold text-app-primary">DSuite</span>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SharedDocumentViewer;