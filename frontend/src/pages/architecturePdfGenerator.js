/**
 * Industry-Grade Architecture Design PDF Generator
 * Exports High-Level Design (HLD) and Low-Level Design (LLD) documents
 * as enterprise-ready PDF publications using jsPDF.
 */
import { jsPDF } from 'jspdf';

// Enterprise color palette
const THEME = {
    primary: [30, 58, 138],       // Deep Blue #1E3A8A
    primaryLight: [238, 242, 255],// Indigo 50
    secondary: [59, 130, 246],    // Blue 500
    text: [31, 41, 55],           // Gray 800
    muted: [100, 116, 139],       // Slate 500
    tableHeaderBg: [30, 58, 138], // Dark Navy
    tableHeaderTxt: [255, 255, 255],
    tableAltRow: [248, 250, 252], // Slate 50
    tableBorder: [226, 232, 240], // Slate 200
    codeBg: [241, 245, 249],      // Slate 100
    codeBorder: [203, 213, 225],  // Slate 300
    badgeBg: [220, 252, 231],     // Emerald 100
    badgeBorder: [134, 239, 172], // Emerald 300
    badgeText: [22, 101, 52]      // Emerald 800
};

/**
 * Normalizes unicode characters to standard ASCII for jsPDF compatibility.
 */
const cleanText = (str) => {
    if (!str) return '';
    return String(str)
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

export const generateArchitectureDesignPDF = async ({
    title = 'Architecture Specification',
    documentType = 'HLD', // 'HLD' or 'LLD'
    markdownContent = '',
    projectName = 'Enterprise System',
    date = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }),
    version = '1.0.0'
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

        const checkPageBreak = (neededHeight) => {
            if (cursorY + neededHeight > pageHeight - bottomMargin) {
                doc.addPage();
                cursorY = topMargin;
                drawRunningHeader();
            }
        };

        const drawRunningHeader = () => {
            const pageNum = doc.internal.getNumberOfPages();
            if (pageNum === 1) return; // Skip cover page header

            doc.setFont('helvetica', 'normal');
            doc.setFontSize(8);
            doc.setTextColor(...THEME.muted);
            const headerTitle = `${documentType.toUpperCase()} SPECIFICATION - ${cleanText(projectName).toUpperCase()}`;
            doc.text(headerTitle, marginLeft, 12);
            doc.text(`CONFIDENTIAL - IEEE 1016`, pageWidth - marginRight, 12, { align: 'right' });

            doc.setDrawColor(...THEME.tableBorder);
            doc.setLineWidth(0.3);
            doc.line(marginLeft, 15, pageWidth - marginRight, 15);
        };

        // ═══════════════════════════════════════════════════════════════════════
        // PAGE 1: TITLE & COVER HEADER
        // ═══════════════════════════════════════════════════════════════════════

        // Top decorative accent bar
        doc.setFillColor(...THEME.secondary);
        doc.rect(marginLeft, cursorY, contentWidth, 3, 'F');
        cursorY += 7;

        // Document Category Tag
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(9);
        doc.setTextColor(...THEME.secondary);
        doc.text(
            documentType === 'LLD' ? 'SOFTWARE ENGINEERING SPECIFICATION' : 'ENTERPRISE ARCHITECTURE FRAMEWORK',
            marginLeft,
            cursorY
        );
        cursorY += 8;

        // Big Document Title
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(22);
        doc.setTextColor(...THEME.primary);
        const titleText = documentType === 'LLD' ? 'Low-Level Design (LLD)' : 'High-Level Design (HLD)';
        doc.text(titleText, marginLeft, cursorY);
        cursorY += 9;

        // Subtitle / Project Name
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(14);
        doc.setTextColor(...THEME.text);
        doc.text(`Project: ${cleanText(projectName)}`, marginLeft, cursorY);
        cursorY += 8;

        // Metadata Info Box
        doc.setFillColor(...THEME.primaryLight);
        doc.setDrawColor(...THEME.tableBorder);
        doc.setLineWidth(0.4);
        doc.roundedRect(marginLeft, cursorY, contentWidth, 24, 2, 2, 'FD');

        doc.setFont('helvetica', 'bold');
        doc.setFontSize(8.5);
        doc.setTextColor(...THEME.primary);
        doc.text(`DOCUMENT ID:`, marginLeft + 5, cursorY + 7);
        doc.text(`STANDARD:`, marginLeft + 5, cursorY + 14);
        doc.text(`RELEASE DATE:`, marginLeft + 5, cursorY + 20);

        doc.setFont('helvetica', 'normal');
        doc.setTextColor(...THEME.text);
        doc.text(`${documentType.toUpperCase()}-${cleanText(projectName).replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 8)}-V${version}`, marginLeft + 35, cursorY + 7);
        doc.text(documentType === 'LLD' ? 'Clean Architecture / OpenAPI 3.1 / ANSI SQL' : 'IEEE 1016-2009 / TOGAF ADM', marginLeft + 35, cursorY + 14);
        doc.text(`${date} | Version ${version}`, marginLeft + 35, cursorY + 20);

        // Status badge inside info box
        doc.setFillColor(...THEME.badgeBg);
        doc.setDrawColor(...THEME.badgeBorder);
        doc.roundedRect(pageWidth - marginRight - 48, cursorY + 5, 42, 14, 1.5, 1.5, 'FD');
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(7.5);
        doc.setTextColor(...THEME.badgeText);
        doc.text('APPROVED FOR', pageWidth - marginRight - 27, cursorY + 10, { align: 'center' });
        doc.text('IMPLEMENTATION', pageWidth - marginRight - 27, cursorY + 15, { align: 'center' });

        cursorY += 32;

        // ═══════════════════════════════════════════════════════════════════════
        // PARSE & RENDER MARKDOWN BODY
        // ═══════════════════════════════════════════════════════════════════════
        const lines = markdownContent.split('\n');
        let inCodeBlock = false;
        let codeBuffer = [];
        let codeLanguage = '';
        let tableBuffer = [];

        const renderTable = (rawTableLines) => {
            if (!rawTableLines || rawTableLines.length < 2) return;
            const rows = [];
            let headers = null;

            rawTableLines.forEach((tLine) => {
                const cells = tLine.split('|')
                    .map(c => cleanText(c.trim()))
                    .filter((c, idx, arr) => idx > 0 && idx < arr.length - 1);

                if (cells.length === 0) return;
                // Skip markdown delimiter line like |:---|:---|
                if (cells.every(c => /^:?-+:?$/.test(c))) return;

                if (!headers) {
                    headers = cells;
                } else {
                    rows.push(cells);
                }
            });

            if (!headers || headers.length === 0) return;

            const colCount = headers.length;
            const colWidth = contentWidth / colCount;

            checkPageBreak(12 + rows.length * 8);

            // Table Header
            doc.setFillColor(...THEME.tableHeaderBg);
            doc.rect(marginLeft, cursorY, contentWidth, 7, 'F');
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(8);
            doc.setTextColor(...THEME.tableHeaderTxt);

            headers.forEach((h, idx) => {
                const cellX = marginLeft + idx * colWidth + 2;
                doc.text(doc.splitTextToSize(h, colWidth - 4)[0] || '', cellX, cursorY + 5);
            });
            cursorY += 7;

            // Table Rows
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(7.5);

            rows.forEach((row, rIdx) => {
                const rowBg = rIdx % 2 === 0 ? THEME.tableAltRow : [255, 255, 255];
                let maxLines = 1;
                const cellTexts = [];

                row.forEach((cellVal, cIdx) => {
                    const wrapped = doc.splitTextToSize(cellVal || '', colWidth - 4);
                    cellTexts.push(wrapped);
                    if (wrapped.length > maxLines) maxLines = wrapped.length;
                });

                const rowHeight = Math.max(6, maxLines * 4 + 2);
                checkPageBreak(rowHeight);

                doc.setFillColor(...rowBg);
                doc.setDrawColor(...THEME.tableBorder);
                doc.setLineWidth(0.2);
                doc.rect(marginLeft, cursorY, contentWidth, rowHeight, 'FD');

                doc.setTextColor(...THEME.text);
                cellTexts.forEach((linesArr, cIdx) => {
                    const cellX = marginLeft + cIdx * colWidth + 2;
                    linesArr.forEach((txtLine, lIdx) => {
                        doc.text(txtLine, cellX, cursorY + 4 + lIdx * 3.8);
                    });
                });

                cursorY += rowHeight;
            });

            cursorY += 4;
        };

        const renderCodeBlock = (linesArr, lang) => {
            if (!linesArr || linesArr.length === 0) return;
            const blockTitle = lang ? `CODE / SPECIFICATION [${lang.toUpperCase()}]` : 'CODE / SPECIFICATION';

            checkPageBreak(14);

            // Code block header tab
            doc.setFillColor(...THEME.muted);
            doc.roundedRect(marginLeft, cursorY, 50, 5, 1, 1, 'F');
            doc.setFont('courier', 'bold');
            doc.setFontSize(6.5);
            doc.setTextColor(255, 255, 255);
            doc.text(blockTitle, marginLeft + 2, cursorY + 3.8);
            cursorY += 5;

            doc.setFont('courier', 'normal');
            doc.setFontSize(7);
            doc.setTextColor(...THEME.text);

            const displayLines = linesArr.slice(0, 150); // Prevent runaway overflow
            const lineHeight = 3.6;
            const totalHeight = displayLines.length * lineHeight + 4;

            checkPageBreak(Math.min(totalHeight, 60));

            // Background box
            doc.setFillColor(...THEME.codeBg);
            doc.setDrawColor(...THEME.codeBorder);
            doc.setLineWidth(0.3);
            doc.rect(marginLeft, cursorY, contentWidth, totalHeight, 'FD');

            displayLines.forEach((cLine, idx) => {
                if (cursorY + 4 > pageHeight - bottomMargin) {
                    doc.addPage();
                    cursorY = topMargin;
                    drawRunningHeader();
                    doc.setFillColor(...THEME.codeBg);
                    doc.setDrawColor(...THEME.codeBorder);
                    doc.setLineWidth(0.3);
                    doc.rect(marginLeft, cursorY, contentWidth, (displayLines.length - idx) * lineHeight + 4, 'FD');
                }
                const truncated = cLine.length > 95 ? cLine.substring(0, 92) + '...' : cLine;
                doc.text(truncated, marginLeft + 3, cursorY + 3.5);
                cursorY += lineHeight;
            });

            cursorY += 6;
        };

        for (let i = 0; i < lines.length; i++) {
            const rawLine = lines[i];
            const trimmed = rawLine.trim();

            // Code block boundary
            if (trimmed.startsWith('```')) {
                if (!inCodeBlock) {
                    inCodeBlock = true;
                    codeLanguage = trimmed.replace(/^```/, '').trim();
                    codeBuffer = [];
                } else {
                    inCodeBlock = false;
                    renderCodeBlock(codeBuffer, codeLanguage);
                    codeBuffer = [];
                    codeLanguage = '';
                }
                continue;
            }

            if (inCodeBlock) {
                codeBuffer.push(cleanText(rawLine));
                continue;
            }

            // Table row detection
            if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
                tableBuffer.push(trimmed);
                continue;
            } else if (tableBuffer.length > 0) {
                renderTable(tableBuffer);
                tableBuffer = [];
            }

            // Skip empty lines with small gap
            if (!trimmed) {
                cursorY += 2;
                continue;
            }

            // Markdown Headings
            if (trimmed.startsWith('# ')) {
                // Main doc title already printed on cover
                continue;
            } else if (trimmed.startsWith('## ')) {
                checkPageBreak(16);
                cursorY += 4;
                doc.setFont('helvetica', 'bold');
                doc.setFontSize(12.5);
                doc.setTextColor(...THEME.primary);
                const headingText = cleanText(trimmed.replace(/^##\s+/, ''));
                doc.text(headingText, marginLeft, cursorY);

                // Section underline
                doc.setDrawColor(...THEME.secondary);
                doc.setLineWidth(0.6);
                doc.line(marginLeft, cursorY + 2, marginLeft + contentWidth, cursorY + 2);
                cursorY += 7;
            } else if (trimmed.startsWith('### ')) {
                checkPageBreak(12);
                cursorY += 3;
                doc.setFont('helvetica', 'bold');
                doc.setFontSize(10);
                doc.setTextColor(...THEME.text);
                const subHeading = cleanText(trimmed.replace(/^###\s+/, ''));
                doc.text(subHeading, marginLeft, cursorY);
                cursorY += 5;
            } else if (trimmed.startsWith('#### ')) {
                checkPageBreak(10);
                cursorY += 2;
                doc.setFont('helvetica', 'bold');
                doc.setFontSize(8.5);
                doc.setTextColor(...THEME.muted);
                const minorHeading = cleanText(trimmed.replace(/^####\s+/, ''));
                doc.text(minorHeading, marginLeft, cursorY);
                cursorY += 4.5;
            } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                // Bullet points
                checkPageBreak(6);
                const bulletText = cleanText(trimmed.substring(2));
                doc.setFont('helvetica', 'normal');
                doc.setFontSize(8.5);
                doc.setTextColor(...THEME.text);

                // Draw bullet dot
                doc.setFillColor(...THEME.secondary);
                doc.circle(marginLeft + 2, cursorY - 1, 0.8, 'F');

                const wrappedBullet = doc.splitTextToSize(bulletText, contentWidth - 6);
                doc.text(wrappedBullet, marginLeft + 5, cursorY);
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

        // Flush any remaining table
        if (tableBuffer.length > 0) {
            renderTable(tableBuffer);
        }

        // ═══════════════════════════════════════════════════════════════════════
        // RUNNING FOOTER ON ALL PAGES
        // ═══════════════════════════════════════════════════════════════════════
        const totalPages = doc.internal.getNumberOfPages();
        for (let p = 1; p <= totalPages; p++) {
            doc.setPage(p);
            doc.setDrawColor(...THEME.tableBorder);
            doc.setLineWidth(0.3);
            doc.line(marginLeft, pageHeight - 12, pageWidth - marginRight, pageHeight - 12);

            doc.setFont('helvetica', 'normal');
            doc.setFontSize(7.5);
            doc.setTextColor(...THEME.muted);
            doc.text('DSuite Enterprise Architecture Engine | Confidential', marginLeft, pageHeight - 8);
            doc.text(`Page ${p} of ${totalPages}`, pageWidth - marginRight, pageHeight - 8, { align: 'right' });
        }

        // Save PDF to user machine
        const safeName = cleanText(projectName).replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 40);
        const fileName = `${safeName}_${documentType.toUpperCase()}_Specification.pdf`;
        doc.save(fileName);
        return true;
    } catch (err) {
        console.error('Failed to generate Architecture Design PDF:', err);
        throw err;
    }
};

export default generateArchitectureDesignPDF;
