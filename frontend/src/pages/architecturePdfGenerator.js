/**
 * Industry-Grade Architecture Design PDF Generator
 * Exports High-Level Design (HLD) and Low-Level Design (LLD) documents
 * as enterprise-ready PDF publications using jsPDF.
 *
 * Fully supports:
 * - High-resolution rasterization and visual embedding of Mermaid, ER & Sequence diagrams
 * - Sequential queue + On-demand rasterization fallback to prevent missing diagram images
 * - Dedicated Executive Cover Page with Document Control & Sign-Off Matrix
 * - Adaptive multi-column data tables with intelligent width weighting
 * - Concrete Physical Repository & File Tree Blueprint with Unicode tree normalization & paginated code boxes
 * - Enterprise typography hierarchy with orphan-prevention page breaks
 * - Multi-page running headers and dynamic two-pass footers (Page X of Y)
 */
import { jsPDF } from 'jspdf';

// Enterprise color palette
export const THEME = {
    primary: [30, 58, 138],          // Deep Enterprise Navy #1E3A8A
    primaryLight: [238, 242, 255],   // Indigo Tint #EEF2FF
    primaryDark: [15, 23, 42],       // Slate 900 #0F172A
    secondary: [59, 130, 246],       // Vibrant Blue #3B82F6
    secondaryLight: [219, 234, 254], // Blue 100 #DBEAFE
    accent: [79, 70, 229],           // Indigo 600 #4F46E5
    text: [31, 41, 55],              // Gray 800 #1F2937
    muted: [100, 116, 139],          // Slate 500 #64748B
    tableHeaderBg: [30, 58, 138],    // Dark Navy
    tableHeaderTxt: [255, 255, 255], // White
    tableAltRow: [248, 250, 252],    // Slate 50 #F8FAFC
    tableBorder: [226, 232, 240],    // Slate 200 #E2E8F0
    cardBg: [248, 250, 252],         // Slate 50 #F8FAFC
    cardBorder: [226, 232, 240],     // Slate 200 #E2E8F0
    codeBg: [241, 245, 249],         // Slate 100 #F1F5F9
    codeBorder: [203, 213, 225],     // Slate 300 #CBD5E1
    badgeBg: [220, 252, 231],        // Emerald 100 #DCFCE7
    badgeBorder: [134, 239, 172],    // Emerald 300 #86EFAC
    badgeText: [22, 101, 52],        // Emerald 800 #166534
    calloutBg: [240, 249, 255],      // Sky 50 #F0F9FF
    calloutBorder: [2, 132, 199],     // Sky 600 #0284C7
    diagramBg: [250, 250, 252],      // Off-white Slate
    diagramBorder: [203, 213, 225]   // Slate 300
};

/**
 * Normalizes Unicode box-drawing and tree characters to clean ASCII representations
 * for jsPDF font compatibility (prevents blank spaces or ? characters).
 */
export const normalizeTreeChars = (text) => {
    if (!text) return '';
    return String(text)
        .replace(/├──/g, '+-- ')
        .replace(/└──/g, '\\-- ')
        .replace(/│/g, '|  ')
        .replace(/─/g, '-')
        .replace(/├/g, '+')
        .replace(/└/g, '\\')
        .replace(/┌/g, '+')
        .replace(/┐/g, '+')
        .replace(/┘/g, '+')
        .replace(/┼/g, '+')
        .replace(/┤/g, '+')
        .replace(/%+\s*%+\s*%+\s*/g, '+-- ')
        .replace(/%+\s+%+\s*%+\s*/g, '|   +-- ')
        .replace(/^%+\s*/gm, '|   ');
};

/**
 * Cleans code lines while strictly PRESERVING leading indentation and converting
 * directory tree graphics to readable ASCII branches.
 */
export const cleanCodeLine = (str) => {
    if (!str) return '';
    const normalized = normalizeTreeChars(str);
    return normalized
        .replace(/[\u2013\u2014]/g, '-')
        .replace(/[\u2018\u2019]/g, "'")
        .replace(/[\u201C\u201D]/g, '"')
        .replace(/[\u2026]/g, '...')
        .replace(/[\u2022\u25E6\u2043]/g, '-')
        .replace(/[\u2192]/g, '->')
        .replace(/[\u2190]/g, '<-')
        .replace(/[\u2264]/g, '<=')
        .replace(/[\u2265]/g, '>=')
        .replace(/[^\x00-\x7F]/g, ' ')
        .replace(/[\r\n]+$/, ''); // Strips only trailing newline, PRESERVING indentation
};

/**
 * Normalizes unicode characters to standard ASCII for jsPDF general text.
 */
export const cleanText = (str) => {
    if (!str) return '';
    return normalizeTreeChars(String(str))
        .replace(/[\u2013\u2014]/g, '-')
        .replace(/[\u2018\u2019]/g, "'")
        .replace(/[\u201C\u201D]/g, '"')
        .replace(/[\u2026]/g, '...')
        .replace(/[\u2022\u25E6\u2043]/g, '-')
        .replace(/[\u2192]/g, '->')
        .replace(/[\u2190]/g, '<-')
        .replace(/[\u2264]/g, '<=')
        .replace(/[\u2265]/g, '>=')
        .replace(/[^\x00-\x7F]/g, ' ')
        .trim();
};

/**
 * Detects whether a code block represents an architectural diagram.
 */
export const isDiagramBlock = (lang, text) => {
    const l = (lang || '').toLowerCase().trim();
    if (['mermaid', 'erdiagram', 'er-diagram', 'flowchart', 'graph', 'sequencediagram', 'sequence', 'classdiagram', 'class', 'statediagram', 'state', 'c4', 'journey', 'gantt', 'pie'].includes(l)) {
        return true;
    }
    const trimmedText = (text || '').trim();
    return /^(sequence\s*diagram|sequencediagram|er\s*diagram|erdiagram|graph|flowchart|class\s*diagram|classdiagram|state\s*diagram|statediagram|c4\w*|journey|gantt|pie)\b/i.test(trimmedText);
};

/**
 * Detects whether an un-fenced line belongs to a directory tree.
 */
export const isTreeLine = (line) => {
    if (!line) return false;
    const t = line.trim();
    if (!t) return false;
    return /^(├──|└──|│|─|\+--|\\--|\|)/.test(t) ||
           t.includes('├──') || t.includes('└──') || t.includes('│   ') ||
           t.includes('+--') || t.includes('\\--') ||
           (/^[\w\.\-\/]+\/$/.test(t) && !t.includes(' ')) ||
           t === '.' || t === './' || t === '.\\' ||
           (/^[\w\.\-]+\.(json|js|ts|jsx|tsx|py|md|yml|yaml|sql|env|dockerignore|gitignore|sh|lock)$/i.test(t));
};

/**
 * Sanitizes Mermaid code to avoid common LLM parser breaks.
 */
export const sanitizeMermaid = (rawCode) => {
    if (!rawCode || typeof rawCode !== 'string') return '';
    let cleaned = rawCode.trim();

    // Strip wrapping markdown code fences if present
    cleaned = cleaned.replace(/^```(?:mermaid|erDiagram|erdiagram|flowchart|graph|sequenceDiagram|sequence|classDiagram|stateDiagram|c4)?\s*/i, '');
    cleaned = cleaned.replace(/\s*```$/, '');
    cleaned = cleaned.trim();

    // Auto-repair common truncations
    cleaned = cleaned.replace(/\bAdministratc\b/gi, 'Administrator');
    cleaned = cleaned.replace(/\bStakehold\b/gi, 'Stakeholders');
    cleaned = cleaned.replace(/\bInteracts via H\b/gi, 'Interacts via HTTPS');
    cleaned = cleaned.replace(/\bValidates ident\b/gi, 'Validates Identity');

    // Fix duplicate diagram headers
    cleaned = cleaned.replace(/^(erDiagram|graph\s+[A-Z]+|flowchart\s+[A-Z]+|sequenceDiagram|classDiagram|stateDiagram)[\s\n]+\1/i, '$1');

    // Detect ER diagrams
    const isEr = cleaned.startsWith('erDiagram') ||
                 cleaned.toLowerCase().startsWith('erdiagram') ||
                 cleaned.includes('||--') ||
                 cleaned.includes('}o--');

    if (isEr && !cleaned.toLowerCase().startsWith('erdiagram')) {
        cleaned = 'erDiagram\n' + cleaned;
    }

    // Detect Sequence diagrams
    const isSeq = cleaned.startsWith('sequenceDiagram') ||
                  cleaned.toLowerCase().startsWith('sequencediagram') ||
                  cleaned.includes('->>') ||
                  cleaned.includes('-->>');

    if (isSeq && !cleaned.toLowerCase().startsWith('sequencediagram')) {
        cleaned = 'sequenceDiagram\n' + cleaned;
    }

    return cleaned;
};

/**
 * Fallback browser-based Mermaid to PNG rasterizer if external renderer not provided.
 */
export const fallbackRenderMermaidToPng = async (mermaidCode) => {
    try {
        if (typeof window === 'undefined' || !window.DOMParser) return null;
        let mermaid;
        try {
            const m = await import('mermaid');
            mermaid = m.default || m;
            mermaid.initialize({
                startOnLoad: false,
                theme: 'neutral',
                securityLevel: 'loose'
            });
        } catch (e) {
            console.warn('Mermaid dynamic import unavailable in current environment:', e);
            return null;
        }

        const uniqueId = `pdf-mmd-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`;
        const cleaned = sanitizeMermaid(mermaidCode);
        let offscreenContainer = null;
        if (typeof document !== 'undefined') {
            offscreenContainer = document.getElementById('mermaid-pdf-fallback-vault');
            if (!offscreenContainer) {
                offscreenContainer = document.createElement('div');
                offscreenContainer.id = 'mermaid-pdf-fallback-vault';
                offscreenContainer.setAttribute('aria-hidden', 'true');
                offscreenContainer.style.cssText = 'position:fixed;top:-99999px;left:-99999px;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none;z-index:-9999;';
                document.body.appendChild(offscreenContainer);
            }
        }
        let renderRes;
        try {
            renderRes = await mermaid.render(uniqueId, cleaned, offscreenContainer || undefined);
        } finally {
            if (offscreenContainer) offscreenContainer.innerHTML = '';
            try {
                const el = document.getElementById(uniqueId);
                if (el && el.parentNode) el.parentNode.removeChild(el);
                const dEl = document.getElementById('d' + uniqueId);
                if (dEl && dEl.parentNode) dEl.parentNode.removeChild(dEl);
            } catch (e) {}
        }
        const svg = renderRes?.svg;
        if (!svg) return null;

        const parser = new DOMParser();
        const svgDoc = parser.parseFromString(svg, 'image/svg+xml');
        const svgEl = svgDoc.querySelector('svg');
        if (!svgEl) return null;

        let targetW = 2400;
        let aspectRatio = 0.55;

        const vb = svgEl.getAttribute('viewBox');
        if (vb) {
            const parts = vb.trim().split(/[\s,]+/);
            if (parts.length === 4) {
                const vbW = parseFloat(parts[2]);
                const vbH = parseFloat(parts[3]);
                if (vbW > 0 && vbH > 0) {
                    aspectRatio = Math.min(vbH / vbW, 2.5);
                }
            }
        }
        const targetH = Math.round(targetW * aspectRatio);
        svgEl.setAttribute('width', String(targetW));
        svgEl.setAttribute('height', String(targetH));

        const modifiedSvg = new XMLSerializer().serializeToString(svgDoc);
        const svgBlob = new Blob([modifiedSvg], { type: 'image/svg+xml;charset=utf-8' });

        return await new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = () => {
                const img = new Image();
                img.onload = () => {
                    try {
                        const canvas = document.createElement('canvas');
                        canvas.width = targetW;
                        canvas.height = targetH;
                        const ctx = canvas.getContext('2d');
                        if (!ctx) { resolve(null); return; }

                        ctx.fillStyle = '#ffffff';
                        ctx.fillRect(0, 0, targetW, targetH);
                        ctx.imageSmoothingEnabled = true;
                        ctx.imageSmoothingQuality = 'high';
                        ctx.drawImage(img, 0, 0, targetW, targetH);

                        const dataUrl = canvas.toDataURL('image/png', 1.0);
                        resolve({ dataUrl, aspectRatio });
                    } catch (err) {
                        console.warn('Canvas rasterization error:', err);
                        resolve(null);
                    }
                };
                img.onerror = () => resolve(null);
                img.src = reader.result;
            };
            reader.onerror = () => resolve(null);
            reader.readAsDataURL(svgBlob);
        });
    } catch (err) {
        console.warn('fallbackRenderMermaidToPng failed:', err);
        return null;
    }
};

/**
 * Generates an Enterprise-Ready Architecture Design PDF.
 */
export const generateArchitectureDesignPDF = async ({
    title = 'Architecture Specification',
    documentType = 'HLD', // 'HLD' or 'LLD'
    markdownContent = '',
    projectName = 'Enterprise System',
    date = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }),
    version = '1.0.0',
    renderMermaidToPng = null
}) => {
    try {
        const doc = new jsPDF({
            orientation: 'portrait',
            unit: 'mm',
            format: 'a4'
        });

        const pageWidth = doc.internal.pageSize.getWidth();
        const pageHeight = doc.internal.pageSize.getHeight();
        const marginLeft = 18;
        const marginRight = 18;
        const contentWidth = pageWidth - marginLeft - marginRight;
        const topMargin = 22;
        const bottomMargin = 20;

        let cursorY = topMargin;

        // ═══════════════════════════════════════════════════════════════════════
        // STEP 1: PRE-SCAN & RASTERIZE MERMAID DIAGRAMS (SEQUENTIAL LIST)
        // ═══════════════════════════════════════════════════════════════════════
        // Automatically close any unclosed markdown code blocks at the document tail
        let sanitizedMarkdown = String(markdownContent || '');
        const effectiveDate = date || new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
        sanitizedMarkdown = sanitizedMarkdown.replace(/(\*\*Date:\*\*)\s*[^\n\r]+/i, `$1 ${effectiveDate}  `);
        const fenceMatches = sanitizedMarkdown.match(/^```/gm) || [];
        if (fenceMatches.length % 2 !== 0) {
            sanitizedMarkdown += '\n```\n';
        }

        const diagramRasterizer = renderMermaidToPng || fallbackRenderMermaidToPng;

        // Comprehensive pre-scan across all markdown code fences
        const fenceRegex = /```(\w*)\s*([\s\S]*?)```/g;
        const preScanDiagramBlocks = [];
        let match;
        while ((match = fenceRegex.exec(sanitizedMarkdown)) !== null) {
            const lang = (match[1] || '').trim();
            const blockContent = match[2];
            if (isDiagramBlock(lang, blockContent)) {
                preScanDiagramBlocks.push(blockContent.trim());
            }
        }

        // Pre-render each diagram in sequence and store in an array
        const preRenderedDiagrams = [];
        for (let i = 0; i < preScanDiagramBlocks.length; i++) {
            const code = preScanDiagramBlocks[i];
            let imgResult = null;
            if (diagramRasterizer) {
                try {
                    imgResult = await diagramRasterizer(code);
                } catch (e) {
                    console.warn(`Diagram ${i + 1} pre-scan rasterization skipped:`, e);
                }
            }
            preRenderedDiagrams.push(imgResult);
        }

        // ═══════════════════════════════════════════════════════════════════════
        // PAGE BREAK & HEADER CONTROLS
        // ═══════════════════════════════════════════════════════════════════════
        const checkPageBreak = (neededHeight) => {
            if (cursorY + neededHeight > pageHeight - bottomMargin) {
                doc.addPage();
                cursorY = topMargin;
                drawRunningHeader();
            }
        };

        const drawRunningHeader = () => {
            const pageNum = doc.internal.getNumberOfPages();
            if (pageNum === 1) return; // Dedicated cover page has no header

            // Document Category & Project on Left
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(7.5);
            doc.setTextColor(...THEME.primary);
            const headerLeft = `${documentType.toUpperCase()} ARCHITECTURE SPECIFICATION | ${cleanText(projectName).toUpperCase()}`;
            doc.text(headerLeft, marginLeft, 12);

            // Classification on Right
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(7.5);
            doc.setTextColor(...THEME.muted);
            doc.text('CONFIDENTIAL & PROPRIETARY', pageWidth - marginRight, 12, { align: 'right' });

            // Accent Rule
            doc.setDrawColor(...THEME.tableBorder);
            doc.setLineWidth(0.3);
            doc.line(marginLeft, 15, pageWidth - marginRight, 15);
        };

        // ═══════════════════════════════════════════════════════════════════════
        // PAGE 1: DEDICATED EXECUTIVE TITLE & COVER PAGE
        // ═══════════════════════════════════════════════════════════════════════
        // Top Classification Ribbon
        doc.setFillColor(...THEME.primary);
        doc.rect(0, 0, pageWidth, 12, 'F');
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(7.5);
        doc.setTextColor(255, 255, 255);
        doc.text('ENTERPRISE ARCHITECTURE SPECIFICATION | STRICTLY CONFIDENTIAL', pageWidth / 2, 8, { align: 'center' });

        cursorY = 28;

        // Decorative Primary Geometric Header Block
        doc.setFillColor(...THEME.primaryLight);
        doc.setDrawColor(...THEME.tableBorder);
        doc.setLineWidth(0.4);
        doc.roundedRect(marginLeft, cursorY, contentWidth, 54, 3, 3, 'FD');

        // Left Vertical Accent Bar
        doc.setFillColor(...THEME.secondary);
        doc.roundedRect(marginLeft, cursorY, 3.5, 54, 1.5, 1.5, 'F');

        // Document Category Tag
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(8.5);
        doc.setTextColor(...THEME.secondary);
        const tagText = documentType === 'LLD'
            ? 'TOGAF / IEEE 1471 COMPLIANT LOW-LEVEL TECHNICAL SPECIFICATION'
            : 'TOGAF / IEEE 1471 COMPLIANT HIGH-LEVEL ARCHITECTURE SPECIFICATION';
        doc.text(tagText, marginLeft + 9, cursorY + 11);

        // Document Title
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(22);
        doc.setTextColor(...THEME.primary);
        const docTitle = documentType === 'LLD'
            ? 'Low-Level Design (LLD)'
            : 'High-Level Design (HLD)';
        doc.text(docTitle, marginLeft + 9, cursorY + 23);

        // Subtitle / Architecture Domain
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(10.5);
        doc.setTextColor(...THEME.text);
        const subTitle = documentType === 'LLD'
            ? 'Component Topology, Database Schemas, API Contracts & Implementation Architecture'
            : 'System Context, Container Architecture, Integration Strategy & Deployment Blueprint';
        doc.text(subTitle, marginLeft + 9, cursorY + 31);

        // Project Identifier Pill
        doc.setFillColor(...THEME.secondaryLight);
        doc.setDrawColor(...THEME.secondary);
        doc.setLineWidth(0.2);
        doc.roundedRect(marginLeft + 9, cursorY + 38, contentWidth - 18, 9, 1.5, 1.5, 'FD');

        doc.setFont('helvetica', 'bold');
        doc.setFontSize(8);
        doc.setTextColor(...THEME.primary);
        doc.text('PROJECT:', marginLeft + 14, cursorY + 44);

        doc.setFont('helvetica', 'normal');
        doc.setTextColor(...THEME.text);
        doc.text(cleanText(projectName), marginLeft + 33, cursorY + 44);

        cursorY += 64;

        // Executive Architecture Abstract Card
        doc.setFillColor(255, 255, 255);
        doc.setDrawColor(...THEME.tableBorder);
        doc.setLineWidth(0.3);
        doc.roundedRect(marginLeft, cursorY, contentWidth, 32, 2, 2, 'FD');

        doc.setFont('helvetica', 'bold');
        doc.setFontSize(9);
        doc.setTextColor(...THEME.primary);
        doc.text('EXECUTIVE ARCHITECTURE ABSTRACT', marginLeft + 8, cursorY + 8);

        doc.setFont('helvetica', 'normal');
        doc.setFontSize(8);
        doc.setTextColor(...THEME.text);
        const abstractDesc = `This enterprise architecture publication establishes the definitive technical blueprint and architectural invariants for ${cleanText(projectName)}. Designed for cloud-native resilience, enterprise scalability, and automated governance compliance, this specification details the target-state topology, service boundaries, data models, and security controls approved for production engineering.`;
        const wrappedAbstract = doc.splitTextToSize(abstractDesc, contentWidth - 16);
        doc.text(wrappedAbstract, marginLeft + 8, cursorY + 14);

        cursorY += 40;

        // Document Control & Metadata Matrix (2-Column Grid)
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(9);
        doc.setTextColor(...THEME.primary);
        doc.text('DOCUMENT CONTROL & METADATA MATRIX', marginLeft, cursorY);
        cursorY += 4;

        const colW = (contentWidth - 6) / 2;
        const rowH = 14;

        const metaLeft = [
            { label: 'DOCUMENT IDENTIFIER', val: `ARC-${documentType}-${new Date().getFullYear()}-001` },
            { label: 'RELEASE DATE', val: date },
            { label: 'REVISION / VERSION', val: `Version ${version}` }
        ];

        const metaRight = [
            { label: 'CLASSIFICATION', val: 'Enterprise Confidential / Internal' },
            { label: 'GOVERNANCE STATUS', val: 'APPROVED FOR IMPLEMENTATION' },
            { label: 'STANDARD FRAMEWORK', val: 'C4-Model & TOGAF Technical Standard' }
        ];

        metaLeft.forEach((m, idx) => {
            const yPos = cursorY + idx * (rowH + 3);
            doc.setFillColor(...THEME.cardBg);
            doc.setDrawColor(...THEME.tableBorder);
            doc.setLineWidth(0.2);
            doc.roundedRect(marginLeft, yPos, colW, rowH, 1.5, 1.5, 'FD');

            doc.setFont('helvetica', 'bold');
            doc.setFontSize(6.5);
            doc.setTextColor(...THEME.muted);
            doc.text(m.label, marginLeft + 6, yPos + 5.5);

            doc.setFont('helvetica', 'bold');
            doc.setFontSize(8.5);
            doc.setTextColor(...THEME.text);
            doc.text(m.val, marginLeft + 6, yPos + 10.5);
        });

        metaRight.forEach((m, idx) => {
            const yPos = cursorY + idx * (rowH + 3);
            const xPos = marginLeft + colW + 6;
            doc.setFillColor(...THEME.cardBg);
            doc.setDrawColor(...THEME.tableBorder);
            doc.setLineWidth(0.2);
            doc.roundedRect(xPos, yPos, colW, rowH, 1.5, 1.5, 'FD');

            doc.setFont('helvetica', 'bold');
            doc.setFontSize(6.5);
            doc.setTextColor(...THEME.muted);
            doc.text(m.label, xPos + 6, yPos + 5.5);

            doc.setFont('helvetica', 'bold');
            doc.setFontSize(8.5);
            if (m.label === 'GOVERNANCE STATUS') {
                doc.setTextColor(...THEME.badgeText);
            } else {
                doc.setTextColor(...THEME.text);
            }
            doc.text(m.val, xPos + 6, yPos + 10.5);
        });

        cursorY += metaLeft.length * (rowH + 3) + 6;

        // Governance Sign-Off Matrix Table
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(9);
        doc.setTextColor(...THEME.primary);
        doc.text('ENTERPRISE ARCHITECTURE REVIEW & SIGN-OFF', marginLeft, cursorY);
        cursorY += 4;

        // Sign-off table header
        doc.setFillColor(...THEME.tableHeaderBg);
        doc.rect(marginLeft, cursorY, contentWidth, 6, 'F');
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(7);
        doc.setTextColor(...THEME.tableHeaderTxt);
        doc.text('ROLE / GOVERNANCE BODY', marginLeft + 4, cursorY + 4.2);
        doc.text('REVIEWER', marginLeft + 65, cursorY + 4.2);
        doc.text('SIGN-OFF STATUS', marginLeft + 125, cursorY + 4.2);
        cursorY += 6;

        const signOffRows = [
            { role: 'Solution Architecture Lead', name: 'DSuite AI Architecture Engine', status: 'VERIFIED & COMPLETE' },
            { role: 'Enterprise Review Board', name: 'Governance & Security Council', status: 'APPROVED' },
            { role: 'Engineering Lead', name: 'Implementation Team', status: 'READY FOR SPRINT' }
        ];

        signOffRows.forEach((r, rIdx) => {
            const rBg = rIdx % 2 === 0 ? THEME.tableAltRow : [255, 255, 255];
            doc.setFillColor(...rBg);
            doc.setDrawColor(...THEME.tableBorder);
            doc.setLineWidth(0.2);
            doc.rect(marginLeft, cursorY, contentWidth, 6.5, 'FD');

            doc.setFont('helvetica', 'normal');
            doc.setFontSize(7.5);
            doc.setTextColor(...THEME.text);
            doc.text(r.role, marginLeft + 4, cursorY + 4.5);
            doc.text(r.name, marginLeft + 65, cursorY + 4.5);

            doc.setFont('helvetica', 'bold');
            doc.setTextColor(...THEME.badgeText);
            doc.text(r.status, marginLeft + 125, cursorY + 4.5);

            cursorY += 6.5;
        });

        // Bottom Cover Confidentiality Notice
        doc.setFont('helvetica', 'italic');
        doc.setFontSize(7);
        doc.setTextColor(...THEME.muted);
        doc.text(
            'This architecture deliverable contains proprietary technical specifications. Unauthorized duplication is strictly prohibited.',
            pageWidth / 2,
            pageHeight - 16,
            { align: 'center' }
        );

        // ═══════════════════════════════════════════════════════════════════════
        // BREAK TO PAGE 2: START MAIN BODY ARCHITECTURE CONTENT
        // ═══════════════════════════════════════════════════════════════════════
        doc.addPage();
        cursorY = topMargin;
        drawRunningHeader();

        // ═══════════════════════════════════════════════════════════════════════
        // RENDER HELPERS: DIAGRAMS, TABLES, CALLOUTS, CODE BLOCKS
        // ═══════════════════════════════════════════════════════════════════════
        let diagramCounter = 1;

        /**
         * Renders a Mermaid diagram as an Enterprise Figure Card.
         * Dual Resolution: Retrieves from pre-rendered sequence queue, or falls back to on-demand rasterization.
         */
        const renderDiagramFigure = async (rawDiagramCode, lang) => {
            const figNum = diagramCounter++;
            const figTitle = `FIGURE ${figNum}: ${documentType.toUpperCase()} SYSTEM ARCHITECTURE TOPOLOGY`;

            // Step 1: Look up by sequential index in preRenderedDiagrams
            let cachedImage = preRenderedDiagrams[figNum - 1] || null;

            // Step 2: Safety Net — On-demand rasterization if missing from pre-scan
            if ((!cachedImage || !cachedImage.dataUrl) && diagramRasterizer) {
                try {
                    cachedImage = await diagramRasterizer(rawDiagramCode);
                } catch (e) {
                    console.warn(`On-demand rasterization failed for Figure ${figNum}:`, e);
                }
            }

            if (cachedImage && cachedImage.dataUrl) {
                // Determine width & height respecting aspect ratio
                const maxCardWidth = contentWidth;
                const innerPadding = 6;
                const imgMaxWidth = maxCardWidth - (innerPadding * 2);
                let imgW = imgMaxWidth;
                let imgH = imgW * (cachedImage.aspectRatio || 0.55);

                // Ensure the diagram does not exceed page limits
                const maxAvailableHeight = pageHeight - topMargin - bottomMargin - 40;
                if (imgH > maxAvailableHeight) {
                    imgH = maxAvailableHeight;
                    imgW = imgH / (cachedImage.aspectRatio || 0.55);
                }

                const cardHeaderH = 9;
                const cardFooterH = 8;
                const totalCardH = imgH + cardHeaderH + cardFooterH + (innerPadding * 2);

                checkPageBreak(totalCardH + 4);

                const cardX = marginLeft;
                const cardY = cursorY;

                // Outer Card Box
                doc.setFillColor(...THEME.diagramBg);
                doc.setDrawColor(...THEME.diagramBorder);
                doc.setLineWidth(0.3);
                doc.roundedRect(cardX, cardY, maxCardWidth, totalCardH, 2, 2, 'FD');

                // Left Blue Accent Ribbon
                doc.setFillColor(...THEME.secondary);
                doc.roundedRect(cardX, cardY, 2.5, totalCardH, 1, 1, 'F');

                // Top Figure Tab
                doc.setFillColor(...THEME.primaryLight);
                doc.roundedRect(cardX + 6, cardY + 3.5, maxCardWidth - 12, 6.5, 1, 1, 'F');
                doc.setFont('helvetica', 'bold');
                doc.setFontSize(7.5);
                doc.setTextColor(...THEME.primary);
                doc.text(figTitle, cardX + 10, cardY + 7.8);

                // Diagram Image - Centered
                const imgX = cardX + (maxCardWidth - imgW) / 2;
                const imgY = cardY + cardHeaderH + innerPadding;

                try {
                    doc.addImage(cachedImage.dataUrl, 'PNG', imgX, imgY, imgW, imgH);
                } catch (e) {
                    console.warn('Failed to draw diagram image in jsPDF:', e);
                }

                // Bottom Caption
                const captionY = cardY + totalCardH - 3.5;
                doc.setFont('helvetica', 'italic');
                doc.setFontSize(7);
                doc.setTextColor(...THEME.muted);
                doc.text(
                    `Figure ${figNum}: High-resolution architectural model generated for ${cleanText(projectName)}`,
                    cardX + maxCardWidth / 2,
                    captionY,
                    { align: 'center' }
                );

                cursorY += totalCardH + 6;
            } else {
                // Fallback architecture placeholder card
                checkPageBreak(28);
                doc.setFillColor(...THEME.cardBg);
                doc.setDrawColor(...THEME.cardBorder);
                doc.setLineWidth(0.3);
                doc.roundedRect(marginLeft, cursorY, contentWidth, 24, 2, 2, 'FD');

                doc.setFillColor(...THEME.secondary);
                doc.rect(marginLeft, cursorY, 2.5, 24, 'F');

                doc.setFont('helvetica', 'bold');
                doc.setFontSize(8.5);
                doc.setTextColor(...THEME.primary);
                doc.text(`[ARCHITECTURAL DIAGRAM: FIGURE ${figNum}]`, marginLeft + 8, cursorY + 8);

                doc.setFont('helvetica', 'normal');
                doc.setFontSize(7.5);
                doc.setTextColor(...THEME.muted);
                doc.text('Visual architecture diagram rendered and accessible in the web workspace.', marginLeft + 8, cursorY + 15);

                cursorY += 30;
            }
        };

        /**
         * Renders an Adaptive Multi-Column Architecture Table.
         */
        const renderTable = (rawTableLines) => {
            if (!rawTableLines || rawTableLines.length < 2) return;
            const rows = [];
            let headers = null;

            rawTableLines.forEach((tLine) => {
                const cells = tLine.split('|')
                    .map(c => cleanText(c.trim()))
                    .filter((c, idx, arr) => idx > 0 && idx < arr.length - 1);

                if (cells.length === 0) return;
                // Skip markdown table delimiter line like |:---|:---|
                if (cells.every(c => /^:?-+:?$/.test(c))) return;

                if (!headers) {
                    headers = cells;
                } else {
                    rows.push(cells);
                }
            });

            if (!headers || headers.length === 0) return;

            // Compute intelligent proportional column widths based on max content length
            const colWeights = headers.map((h, colIdx) => {
                let maxLen = h.length;
                rows.forEach(r => {
                    if (r[colIdx]) maxLen = Math.max(maxLen, Math.min(r[colIdx].length, 80));
                });
                return Math.max(maxLen, 6);
            });
            const totalWeight = colWeights.reduce((a, b) => a + b, 0);
            const rawColWidths = colWeights.map(w => Math.max((w / totalWeight) * contentWidth, 22));
            const sumWidths = rawColWidths.reduce((a, b) => a + b, 0);
            const scale = contentWidth / sumWidths;
            const colWidths = rawColWidths.map(w => w * scale);

            checkPageBreak(14 + Math.min(rows.length * 7, 40));

            // Table Header Row
            doc.setFillColor(...THEME.tableHeaderBg);
            doc.rect(marginLeft, cursorY, contentWidth, 7, 'F');
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(7.5);
            doc.setTextColor(...THEME.tableHeaderTxt);

            let currentX = marginLeft;
            headers.forEach((h, idx) => {
                const cWidth = colWidths[idx];
                const cellX = currentX + 2.5;
                const wrappedH = doc.splitTextToSize(h, cWidth - 5);
                doc.text(wrappedH[0] || '', cellX, cursorY + 4.8);
                currentX += cWidth;
            });
            cursorY += 7;

            // Table Data Rows
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(7.5);

            rows.forEach((row, rIdx) => {
                const rowBg = rIdx % 2 === 0 ? THEME.tableAltRow : [255, 255, 255];
                let maxLines = 1;
                const cellTexts = [];

                row.forEach((cellVal, cIdx) => {
                    const cWidth = colWidths[cIdx] || (contentWidth / headers.length);
                    const wrapped = doc.splitTextToSize(cellVal || '', cWidth - 5);
                    cellTexts.push(wrapped);
                    if (wrapped.length > maxLines) maxLines = wrapped.length;
                });

                const rowHeight = Math.max(6.5, maxLines * 4 + 2);
                checkPageBreak(rowHeight);

                // Row background & border
                doc.setFillColor(...rowBg);
                doc.setDrawColor(...THEME.tableBorder);
                doc.setLineWidth(0.2);
                doc.rect(marginLeft, cursorY, contentWidth, rowHeight, 'FD');

                doc.setTextColor(...THEME.text);
                let cellLeft = marginLeft;
                cellTexts.forEach((linesArr, cIdx) => {
                    const cWidth = colWidths[cIdx] || (contentWidth / headers.length);
                    const cellX = cellLeft + 2.5;
                    linesArr.forEach((txtLine, lIdx) => {
                        doc.text(txtLine, cellX, cursorY + 4 + lIdx * 3.8);
                    });
                    cellLeft += cWidth;
                });

                cursorY += rowHeight;
            });

            cursorY += 5;
        };

        /**
         * Renders Code/Specification Blocks & Directory Trees across paginated slices.
         * Preserves indentation and handles multi-page repository trees cleanly.
         */
        const renderCodeBlock = (linesArr, lang) => {
            if (!linesArr || linesArr.length === 0) return;
            const blockTitle = lang ? `TECHNICAL SPECIFICATION [${lang.toUpperCase()}]` : 'PHYSICAL REPOSITORY & FILE TREE SPECIFICATION';

            checkPageBreak(18);

            // Code block header tab
            doc.setFillColor(...THEME.muted);
            doc.roundedRect(marginLeft, cursorY, 82, 5.5, 1, 1, 'F');
            doc.setFont('courier', 'bold');
            doc.setFontSize(6.5);
            doc.setTextColor(255, 255, 255);
            doc.text(blockTitle, marginLeft + 3, cursorY + 4);
            cursorY += 6;

            doc.setFont('courier', 'normal');
            doc.setFontSize(7);
            doc.setTextColor(...THEME.text);

            const displayLines = linesArr.slice(0, 1500); // Generous line limit for comprehensive repository trees
            const lineHeight = 3.6;

            let lineIdx = 0;
            while (lineIdx < displayLines.length) {
                // Calculate how many lines can fit on current page without overflowing
                const availableHeight = pageHeight - bottomMargin - cursorY - 4;
                const linesToFit = Math.max(1, Math.floor(availableHeight / lineHeight));
                const chunkLines = displayLines.slice(lineIdx, lineIdx + linesToFit);
                const chunkHeight = chunkLines.length * lineHeight + 4;

                // Draw background box for this specific page slice
                doc.setFillColor(...THEME.codeBg);
                doc.setDrawColor(...THEME.codeBorder);
                doc.setLineWidth(0.3);
                doc.rect(marginLeft, cursorY, contentWidth, chunkHeight, 'FD');

                // Print the lines for this chunk with indentation preserved
                chunkLines.forEach((cLine) => {
                    const cleanedLine = cleanCodeLine(cLine);
                    const truncated = cleanedLine.length > 95 ? cleanedLine.substring(0, 92) + '...' : cleanedLine;
                    doc.text(truncated, marginLeft + 3, cursorY + 3.5);
                    cursorY += lineHeight;
                });

                cursorY += 4;
                lineIdx += chunkLines.length;

                // If more lines remain in this block, page break cleanly and add continuation tab
                if (lineIdx < displayLines.length) {
                    doc.addPage();
                    cursorY = topMargin;
                    drawRunningHeader();

                    doc.setFillColor(...THEME.muted);
                    doc.roundedRect(marginLeft, cursorY, 82, 5, 1, 1, 'F');
                    doc.setFont('courier', 'bold');
                    doc.setFontSize(6);
                    doc.setTextColor(255, 255, 255);
                    doc.text(`${blockTitle} (CONT.)`, marginLeft + 3, cursorY + 3.8);
                    cursorY += 6;

                    doc.setFont('courier', 'normal');
                    doc.setFontSize(7);
                    doc.setTextColor(...THEME.text);
                }
            }

            cursorY += 4;
        };

        /**
         * Renders Architectural Callout Cards for Blockquotes / Notes.
         */
        const renderCalloutCard = (text) => {
            checkPageBreak(18);
            const wrapped = doc.splitTextToSize(cleanText(text), contentWidth - 14);
            const cardHeight = Math.max(12, wrapped.length * 4.2 + 6);

            doc.setFillColor(...THEME.calloutBg);
            doc.setDrawColor(...THEME.calloutBorder);
            doc.setLineWidth(0.3);
            doc.roundedRect(marginLeft, cursorY, contentWidth, cardHeight, 1.5, 1.5, 'FD');

            // Left vertical blue border
            doc.setFillColor(...THEME.calloutBorder);
            doc.rect(marginLeft, cursorY, 2.5, cardHeight, 'F');

            doc.setFont('helvetica', 'normal');
            doc.setFontSize(8);
            doc.setTextColor(...THEME.primary);
            doc.text(wrapped, marginLeft + 7, cursorY + 5.5);

            cursorY += cardHeight + 4;
        };

        // ═══════════════════════════════════════════════════════════════════════
        // STEP 2: PARSE & RENDER MARKDOWN BODY SEQUENTIALLY
        // ═══════════════════════════════════════════════════════════════════════
        const lines = sanitizedMarkdown.split('\n');
        let inCodeBlock = false;
        let codeBuffer = [];
        let codeLanguage = '';
        let tableBuffer = [];
        let treeBuffer = [];
        let inRepositorySection = false;
        let hasEncounteredFirstSection = false;

        for (let i = 0; i < lines.length; i++) {
            const rawLine = lines[i];
            const trimmed = rawLine.trim();

            // Code block boundary detection
            if (trimmed.startsWith('```')) {
                // Flush any pending treeBuffer before entering/exiting code block
                if (treeBuffer.length > 0) {
                    renderCodeBlock(treeBuffer, 'REPOSITORY TREE');
                    treeBuffer = [];
                }

                if (!inCodeBlock) {
                    inCodeBlock = true;
                    codeLanguage = trimmed.replace(/^```/, '').trim().toLowerCase();
                    codeBuffer = [];
                } else {
                    inCodeBlock = false;
                    const blockContent = codeBuffer.join('\n');
                    const isDiagram = isDiagramBlock(codeLanguage, blockContent);

                    if (isDiagram) {
                        // RENDER VISUAL ARCHITECTURE DIAGRAM FIGURE
                        await renderDiagramFigure(blockContent, codeLanguage);
                    } else {
                        // Standard technical specification / repository tree code block
                        const defaultLang = inRepositorySection ? 'REPOSITORY TREE' : '';
                        renderCodeBlock(codeBuffer, codeLanguage || defaultLang);
                    }
                    codeBuffer = [];
                    codeLanguage = '';
                }
                continue;
            }

            if (inCodeBlock) {
                // Keep raw line with indentation intact for code and diagrams
                codeBuffer.push(rawLine);
                continue;
            }

            // Table row detection
            if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
                if (treeBuffer.length > 0) {
                    renderCodeBlock(treeBuffer, 'REPOSITORY TREE');
                    treeBuffer = [];
                }
                tableBuffer.push(trimmed);
                continue;
            } else if (tableBuffer.length > 0) {
                renderTable(tableBuffer);
                tableBuffer = [];
            }

            // Directory / Repository File Tree line detection outside code blocks
            if (isTreeLine(rawLine) || (inRepositorySection && rawLine.startsWith('    '))) {
                treeBuffer.push(rawLine);
                continue;
            } else if (inRepositorySection && treeBuffer.length > 0 && !trimmed) {
                // Peek ahead: if following non-empty line is also part of directory tree, retain blank line
                let hasMoreTree = false;
                for (let k = i + 1; k < Math.min(lines.length, i + 6); k++) {
                    const peekTrimmed = lines[k].trim();
                    if (!peekTrimmed) continue;
                    if (isTreeLine(lines[k]) || lines[k].startsWith('    ')) {
                        hasMoreTree = true;
                    }
                    break;
                }
                if (hasMoreTree) {
                    treeBuffer.push('');
                    continue;
                }
            } else if (treeBuffer.length > 0) {
                renderCodeBlock(treeBuffer, 'REPOSITORY TREE');
                treeBuffer = [];
            }

            // Before the first major section (## ...), filter out redundant document metadata headers
            // (e.g. Date, Version, Author, Status) and decorative separators (---) as they are already
            // officially formatted in the Page 1 Executive Title & Metadata Matrix.
            if (!hasEncounteredFirstSection) {
                if (trimmed.startsWith('## ')) {
                    hasEncounteredFirstSection = true;
                } else {
                    if (trimmed.startsWith('# ')) {
                        continue;
                    }
                    if (/^\*\*(?:Date|Version|Document\s*Version|Release\s*Date|Author|Status|Project|Document\s*Title):\*\*/i.test(trimmed) ||
                        /^(?:Date|Version|Document\s*Version|Release\s*Date|Author|Status|Project|Document\s*Title):\s*/i.test(trimmed)) {
                        continue;
                    }
                    if (/^(?:---|\*\*\*|___)\s*$/.test(trimmed)) {
                        continue;
                    }
                    if (!trimmed) {
                        continue;
                    }
                }
            }

            // Skip empty lines with small gap
            if (!trimmed) {
                cursorY += 2;
                continue;
            }

            // Architectural horizontal divider rule (post-cover)
            if (/^(?:---|\*\*\*|___)\s*$/.test(trimmed)) {
                if (hasEncounteredFirstSection) {
                    checkPageBreak(8);
                    doc.setDrawColor(...THEME.tableBorder);
                    doc.setLineWidth(0.3);
                    doc.line(marginLeft, cursorY + 2, marginLeft + contentWidth, cursorY + 2);
                    cursorY += 6;
                }
                continue;
            }

            // Architectural Callout / Blockquote
            if (trimmed.startsWith('>')) {
                const calloutText = trimmed.replace(/^>\s*/, '').replace(/\[!(NOTE|IMPORTANT|TIP|WARNING)\]/i, '').trim();
                renderCalloutCard(calloutText);
                continue;
            }

            // Markdown Headings
            if (trimmed.startsWith('# ')) {
                // Main doc title already printed on Executive Cover Page
                // If in Repository section and it's a repository title like "# Project Repository Structure", capture it
                if (inRepositorySection) {
                    treeBuffer.push(trimmed);
                }
                continue;
            } else if (trimmed.startsWith('## ')) {
                hasEncounteredFirstSection = true;
                // Check if entering or leaving Repository & File Tree Blueprint Section
                const lowerHeading = trimmed.toLowerCase();
                inRepositorySection = lowerHeading.includes('concrete physical repository') ||
                                      lowerHeading.includes('file tree blueprint') ||
                                      lowerHeading.includes('repository structure');

                // Section Heading 2: Smart Orphan Prevention
                checkPageBreak(38);
                cursorY += 5;

                // Section badge indicator
                doc.setFillColor(...THEME.primaryLight);
                doc.roundedRect(marginLeft, cursorY - 3, contentWidth, 8, 1, 1, 'F');
                doc.setFillColor(...THEME.secondary);
                doc.rect(marginLeft, cursorY - 3, 2.5, 8, 'F');

                doc.setFont('helvetica', 'bold');
                doc.setFontSize(11.5);
                doc.setTextColor(...THEME.primary);
                const headingText = cleanText(trimmed.replace(/^##\s+/, '')).toUpperCase();
                doc.text(headingText, marginLeft + 6, cursorY + 2.5);

                cursorY += 10;
            } else if (trimmed.startsWith('### ')) {
                // Subheading 3:
                checkPageBreak(22);
                cursorY += 3;
                doc.setFont('helvetica', 'bold');
                doc.setFontSize(10);
                doc.setTextColor(...THEME.text);
                const subHeading = cleanText(trimmed.replace(/^###\s+/, ''));
                doc.text(subHeading, marginLeft, cursorY);

                // Subtle underline
                doc.setDrawColor(...THEME.tableBorder);
                doc.setLineWidth(0.3);
                doc.line(marginLeft, cursorY + 2, marginLeft + contentWidth, cursorY + 2);
                cursorY += 6;
            } else if (trimmed.startsWith('#### ')) {
                // Minor Heading 4:
                checkPageBreak(14);
                cursorY += 2;
                doc.setFont('helvetica', 'bold');
                doc.setFontSize(8.5);
                doc.setTextColor(...THEME.muted);
                const minorHeading = cleanText(trimmed.replace(/^####\s+/, ''));
                doc.text(minorHeading, marginLeft, cursorY);
                cursorY += 4.5;
            } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                // Bullet points with colored dot marker
                checkPageBreak(7);
                const bulletText = cleanText(trimmed.substring(2));
                doc.setFont('helvetica', 'normal');
                doc.setFontSize(8.5);
                doc.setTextColor(...THEME.text);

                doc.setFillColor(...THEME.secondary);
                doc.circle(marginLeft + 2.5, cursorY - 1, 0.8, 'F');

                const wrappedBullet = doc.splitTextToSize(bulletText, contentWidth - 7);
                doc.text(wrappedBullet, marginLeft + 6, cursorY);
                cursorY += wrappedBullet.length * 4.2;
            } else {
                // Standard Paragraph
                checkPageBreak(8);
                doc.setFont('helvetica', 'normal');
                doc.setFontSize(8.5);
                doc.setTextColor(...THEME.text);
                const wrappedParagraph = doc.splitTextToSize(cleanText(trimmed), contentWidth);
                doc.text(wrappedParagraph, marginLeft, cursorY);
                cursorY += wrappedParagraph.length * 4.2;
            }
        }

        // Flush any remaining code, tree or table buffers at document end (crucial for unclosed fences/EOF trees)
        if (codeBuffer.length > 0) {
            const blockContent = codeBuffer.join('\n');
            const isDiagram = isDiagramBlock(codeLanguage, blockContent);
            if (isDiagram) {
                await renderDiagramFigure(blockContent, codeLanguage);
            } else {
                renderCodeBlock(codeBuffer, codeLanguage || (inRepositorySection ? 'REPOSITORY TREE' : ''));
            }
            codeBuffer = [];
            inCodeBlock = false;
        }
        if (treeBuffer.length > 0) {
            renderCodeBlock(treeBuffer, 'REPOSITORY TREE');
            treeBuffer = [];
        }
        if (tableBuffer.length > 0) {
            renderTable(tableBuffer);
            tableBuffer = [];
        }

        // ═══════════════════════════════════════════════════════════════════════
        // STEP 3: RUNNING FOOTERS ON ALL PAGES (TWO-PASS TOTAL PAGE NUMBERING)
        // ═══════════════════════════════════════════════════════════════════════
        const totalPages = doc.internal.getNumberOfPages();
        for (let p = 1; p <= totalPages; p++) {
            doc.setPage(p);

            // Footer separator line
            doc.setDrawColor(...THEME.tableBorder);
            doc.setLineWidth(0.3);
            doc.line(marginLeft, pageHeight - 12, pageWidth - marginRight, pageHeight - 12);

            // Left: Engine & Confidentiality
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(7.5);
            doc.setTextColor(...THEME.muted);
            doc.text('DSuite Enterprise Architecture Engine | Automated Deliverable', marginLeft, pageHeight - 7.5);

            // Right: Page X of Y
            doc.setFont('helvetica', 'bold');
            doc.text(`Page ${p} of ${totalPages}`, pageWidth - marginRight, pageHeight - 7.5, { align: 'right' });
        }

        // ═══════════════════════════════════════════════════════════════════════
        // STEP 4: TRIGGER BROWSER DOWNLOAD
        // ═══════════════════════════════════════════════════════════════════════
        const safeName = cleanText(projectName).replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 40) || 'Enterprise_Solution';
        const fileName = `${safeName}_${documentType.toUpperCase()}_Specification.pdf`;

        if (typeof window !== 'undefined' && doc.save) {
            doc.save(fileName);
        }

        return { success: true, doc, totalPages, fileName };
    } catch (err) {
        console.error('Failed to generate Architecture Design PDF:', err);
        throw err;
    }
};

export default generateArchitectureDesignPDF;
