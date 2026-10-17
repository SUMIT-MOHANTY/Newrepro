/**
 * Robust PDF Generation Module
 *
 * This module provides AI-model-agnostic PDF generation that works regardless
 * of which AI model generates the content (Claude, GPT, Llama, etc.).
 *
 * Key Features:
 * 1. Smart table parsing and rendering
 * 2. Mermaid diagram extraction and rendering
 * 3. Unicode character preservation (with fallbacks)
 * 4. Consistent formatting across AI models
 */

import { jsPDF } from 'jspdf';

// Color palette for consistent styling
const PALETTE = {
    primary: '#1E3A8A',
    primarySoft: '#E8EEFF',
    border: '#D6E0F5',
    text: '#1F2937',
    muted: '#64748B',
    tableHeader: '#1E3A8A',
    tableHeaderText: '#FFFFFF',
    tableRowAlt: '#F8FAFC',
    tableBorder: '#E2E8F0',
    verdictGo: { fill: '#DCFCE7', border: '#86EFAC', text: '#166534' },
    verdictNoGo: { fill: '#FEE2E2', border: '#FCA5A5', text: '#B91C1C' },
    verdictCaution: { fill: '#FEF3C7', border: '#FCD34D', text: '#B45309' },
};

// ═══════════════════════════════════════════════════════════════════════════
// UTILITY FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Safely parse hex color to RGB array
 */
const parseHex = (hex) => {
    const normalized = String(hex || '').replace('#', '').trim();
    const full = normalized.length === 3
        ? normalized.split('').map((char) => char + char).join('')
        : normalized;
    const intValue = Number.parseInt(full || '000000', 16);
    return [
        (intValue >> 16) & 255,
        (intValue >> 8) & 255,
        intValue & 255
    ];
};

/**
 * Normalize Unicode characters to ASCII-safe equivalents
 * Preserves readable special characters while ensuring PDF compatibility
 */
const normalizeUnicode = (text) => {
    if (!text) return '';

    return String(text)
        // Preserve dashes but normalize em/en dashes to hyphens
        .replace(/[\u2013\u2014\u2015]/g, '-')
        // Normalize smart quotes to regular quotes
        .replace(/[\u2018\u2019]/g, "'")
        .replace(/[\u201C\u201D]/g, '"')
        // Normalize ellipsis
        .replace(/\u2026/g, '...')
        // Normalize bullet points to hyphens
        .replace(/[\u2022\u2023\u2043\u25E6\u25AA\u25AB]/g, '-')
        // Normalize math symbols
        .replace(/\u2264/g, '<=')
        .replace(/\u2265/g, '>=')
        .replace(/\u00B2/g, '2')  // Superscript 2
        .replace(/\u00B3/g, '3')  // Superscript 3
        // Preserve accented characters that are common (only safe ones)
        .replace(/[\u00C0-\u00FF]/g, (match) => match)  // Latin-1 Supplement
        // Remove remaining problematic Unicode
        .replace(/[\u2000-\u200B]/g, ' ')  // Invisible spaces
        .replace(/[^\x00-\uFFFF]/g, (match) => {
            // Only keep truly safe Unicode (basic multilingual plane)
            return match;
        })
        .trim();
};

/**
 * Extract and parse Markdown tables from text
 * Handles multiple table formats from different AI models
 */
const extractTables = (text) => {
    const tables = [];
    const lines = text.split('\n');
    let currentTable = null;
    let inCodeBlock = false;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];

        // Track code blocks
        if (line.trim().startsWith('```')) {
            inCodeBlock = !inCodeBlock;
            continue;
        }
        if (inCodeBlock) continue;

        // Skip mermaid diagrams
        if (line.trim().startsWith('```mermaid') || line.trim().startsWith('flowchart') || line.trim().startsWith('graph')) {
            continue;
        }

        // Table detection: starts with | and has multiple |
        if (line.includes('|') && line.split('|').length >= 3) {
            const cells = line.split('|').filter(c => c.trim()).map(c => c.trim());

            // Skip separator lines (---|:---|)
            if (cells.every(c => /^-+$/.test(c) || /^:+-+:+$/.test(c))) {
                if (currentTable) {
                    currentTable.hasSeparator = true;
                }
                continue;
            }

            // Start new table if not in one
            if (!currentTable) {
                currentTable = {
                    headers: cells,
                    rows: [],
                    startLine: i
                };
            } else {
                currentTable.rows.push(cells);
            }
        } else if (currentTable) {
            // End of table
            tables.push(currentTable);
            currentTable = null;
        }
    }

    // Push last table if exists
    if (currentTable) {
        tables.push(currentTable);
    }

    return tables;
};

/**
 * Extract Mermaid diagram code blocks from text
 */
const extractMermaidDiagrams = (text) => {
    const diagrams = [];
    const regex = /```mermaid\n?([\s\S]*?)```/gi;
    let match;

    while ((match = regex.exec(text)) !== null) {
        diagrams.push({
            code: match[1].trim(),
            index: match.index
        });
    }

    return diagrams;
};

/**
 * Remove code blocks from text (for plain text rendering)
 */
const stripCodeBlocks = (text) => {
    return text
        .replace(/```[\s\S]*?```/g, '[Diagram]')
        .replace(/`[^`]+`/g, (match) => match.replace(/`/g, ''))
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');  // Links -> text
};

/**
 * Normalize text for PDF rendering with intelligent formatting preservation
 */
const normalizeForPdf = (text, options = {}) => {
    const {
        preserveNewlines = true,
        stripMarkdownHeadings = false,
        stripEmphasis = false
    } = options;

    if (!text) return '';

    return String(text)
        // Handle code blocks - extract mermaid but strip other code
        .replace(/```mermaid\n?([\s\S]*?)```/gi, '\n[MERMAID_DIAGRAM]\n')
        .replace(/```[\s\S]*?```/gi, '')
        .replace(/`([^`]+)`/g, '$1')

        // Handle links
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')

        // Handle headings
        .replace(/^#{1,6}\s*/gm, stripMarkdownHeadings ? '' : '## ')

        // Handle emphasis
        .replace(/\*\*(.*?)\*\*/g, stripEmphasis ? '$1' : '**$1**')
        .replace(/\*(.*?)\*/g, stripEmphasis ? '$1' : '*$1*')
        .replace(/__(.*?)__/g, '$1')
        .replace(/_(.*?)_/g, '$1')

        // Handle HTML tags
        .replace(/<\s*br\s*\/?>/gi, '\n')
        .replace(/<\/\s*(p|div|h[1-6]|section|article)\s*>/gi, '\n\n')
        .replace(/<[^>]+>/g, '')

        // Handle HTML entities
        .replace(/&nbsp;/gi, ' ')
        .replace(/&amp;/gi, '&')
        .replace(/&lt;/gi, '<')
        .replace(/&gt;/gi, '>')
        .replace(/&quot;/gi, '"')
        .replace(/&#39;/gi, "'")
        .replace(/&#x27;/gi, "'")

        // Normalize Unicode
        .replace(/[\u2018\u2019]/g, "'")
        .replace(/[\u201C\u201D]/g, '"')
        .replace(/[\u2013\u2014\u2015]/g, '-')
        .replace(/\u2026/g, '...')
        .replace(/\u2264/g, '<=')
        .replace(/\u2265/g, '>=')
        .replace(/[\u2000-\u200B]/g, ' ')
        .replace(/[\u2022\u2023\u2043]/g, '-')

        // Clean up whitespace
        .replace(/\r/g, '')
        .replace(/\n{3,}/g, preserveNewlines ? '\n\n' : ' ')
        .trim();
};

/**
 * Split text into logical sections while preserving structure
 */
const splitIntoSections = (text) => {
    const sections = [];
    const lines = text.split('\n');

    let currentSection = {
        type: 'paragraph',
        content: []
    };

    for (const line of lines) {
        const trimmed = line.trim();

        // Check for section headings
        if (/^#{1,3}\s/.test(trimmed)) {
            if (currentSection.content.length > 0) {
                sections.push({ ...currentSection, content: currentSection.content.join('\n') });
            }
            currentSection = {
                type: 'heading',
                level: (trimmed.match(/^(#+)/)[1] || '').length,
                content: [trimmed.replace(/^#+\s*/, '')]
            };
        }
        // Check for list items
        else if (/^[-*+]\s/.test(trimmed) || /^\d+\.\s/.test(trimmed)) {
            if (currentSection.type !== 'list') {
                if (currentSection.content.length > 0) {
                    sections.push({ ...currentSection, content: currentSection.content.join('\n') });
                }
                currentSection = { type: 'list', content: [] };
            }
            currentSection.content.push(trimmed);
        }
        // Check for table rows (will be processed separately)
        else if (trimmed.includes('|') && trimmed.split('|').filter(c => c.trim()).length >= 3) {
            if (currentSection.type !== 'table' && currentSection.content.length > 0) {
                sections.push({ ...currentSection, content: currentSection.content.join('\n') });
            }
            currentSection = { type: 'table', content: [trimmed] };
        }
        // Empty lines
        else if (!trimmed) {
            if (currentSection.content.length > 0 && currentSection.type !== 'paragraph') {
                sections.push({ ...currentSection, content: currentSection.content.join('\n') });
                currentSection = { type: 'paragraph', content: [] };
            }
        }
        // Regular text
        else {
            if (currentSection.type === 'table' && currentSection.content.length > 0) {
                sections.push({ ...currentSection, content: currentSection.content.join('\n') });
                currentSection = { type: 'paragraph', content: [] };
            }
            currentSection.content.push(trimmed);
        }
    }

    // Push remaining section
    if (currentSection.content.length > 0) {
        sections.push({ ...currentSection, content: currentSection.content.join('\n') });
    }

    return sections;
};

// ═══════════════════════════════════════════════════════════════════════════
// PDF COMPONENT FACTORY
// ═══════════════════════════════════════════════════════════════════════════

class PdfComponents {
    constructor(pdf, options = {}) {
        this.pdf = pdf;
        this.pageWidth = pdf.internal.pageSize.getWidth();
        this.pageHeight = pdf.internal.pageSize.getHeight();
        this.marginX = options.marginX || 14;
        this.bottomMargin = options.bottomMargin || 14;
        this.contentWidth = this.pageWidth - this.marginX * 2;
        this.cursorY = options.startY || 0;
        this.topBandHeight = options.topBandHeight || 22;

        this.palette = PALETTE;
    }

    setTextColor(hex) {
        const [r, g, b] = parseHex(hex);
        this.pdf.setTextColor(r, g, b);
    }

    setFillColor(hex) {
        const [r, g, b] = parseHex(hex);
        this.pdf.setFillColor(r, g, b);
    }

    setDrawColor(hex) {
        const [r, g, b] = parseHex(hex);
        this.pdf.setDrawColor(r, g, b);
    }

    ensureSpace(requiredHeight = 10) {
        if (this.cursorY + requiredHeight > this.pageHeight - this.bottomMargin) {
            this.pdf.addPage();
            this.drawHeader();
            return true;
        }
        return false;
    }

    drawHeader(title = 'Analysis Report', docLabel = '') {
        this.setFillColor(this.palette.primary);
        this.pdf.rect(0, 0, this.pageWidth, this.topBandHeight, 'F');

        this.pdf.setFont('helvetica', 'bold');
        this.pdf.setFontSize(13);
        this.pdf.setTextColor(255, 255, 255);
        this.pdf.text(title, this.marginX, 9);

        this.pdf.setFont('helvetica', 'normal');
        this.pdf.setFontSize(8);
        if (docLabel) {
            const label = docLabel.slice(0, 72);
            this.pdf.text(label, this.marginX, 15);
        }

        const dateLabel = `Generated ${new Date().toLocaleString('en-IN')}`;
        const dateWidth = this.pdf.getTextWidth(dateLabel);
        this.pdf.text(dateLabel, this.pageWidth - this.marginX - dateWidth, 15);

        this.cursorY = this.topBandHeight + 8;
        this.setTextColor(this.palette.text);
    }

    drawFooter() {
        const totalPages = this.pdf.getNumberOfPages();
        for (let page = 1; page <= totalPages; page += 1) {
            this.pdf.setPage(page);
            this.pdf.setFont('helvetica', 'normal');
            this.pdf.setFontSize(8);
            this.setTextColor('#94A3B8');
            const footerLabel = `Page ${page} of ${totalPages}`;
            const footerWidth = this.pdf.getTextWidth(footerLabel);
            this.pdf.text(footerLabel, this.pageWidth - this.marginX - footerWidth, this.pageHeight - 6);
        }
    }

    addSectionTitle(title, options = {}) {
        const { height = 8, fontSize = 10.5 } = options;
        this.ensureSpace(height + 6);

        this.setFillColor(this.palette.primarySoft);
        this.setDrawColor(this.palette.border);
        this.pdf.roundedRect(this.marginX, this.cursorY, this.contentWidth, height, 1.5, 1.5, 'FD');

        this.setTextColor(this.palette.primary);
        this.pdf.setFont('helvetica', 'bold');
        this.pdf.setFontSize(fontSize);
        this.pdf.text(normalizeUnicode(title), this.marginX + 3, this.cursorY + 5.4);

        this.cursorY += height + 3;
        this.pdf.setFont('helvetica', 'normal');
        this.pdf.setFontSize(10);
        this.setTextColor(this.palette.text);
    }

    addParagraphs(text, options = {}) {
        const {
            fontSize = 10,
            lineHeight = 4.8,
            color = this.palette.text,
            bold = false,
            indent = 0
        } = options;

        if (!text) return;

        const blocks = String(text)
            .split(/\n{2,}/)
            .map(b => b.trim())
            .filter(Boolean);

        if (!blocks.length) return;

        this.pdf.setFont('helvetica', bold ? 'bold' : 'normal');
        this.pdf.setFontSize(fontSize);
        this.setTextColor(color);

        const effectiveContentWidth = this.contentWidth - indent;

        blocks.forEach((block, blockIndex) => {
            const lines = this.pdf.splitTextToSize(block, effectiveContentWidth);
            lines.forEach(line => {
                this.ensureSpace(lineHeight);
                this.pdf.setFont('helvetica', bold ? 'bold' : 'normal');
                this.pdf.setFontSize(fontSize);
                this.setTextColor(color);
                this.pdf.text(line, this.marginX + indent, this.cursorY);
                this.cursorY += lineHeight;
            });

            if (blockIndex < blocks.length - 1) {
                this.cursorY += 1.5;
            }
        });

        this.pdf.setFont('helvetica', 'normal');
        this.setTextColor(this.palette.text);
    }

    addTable(tableData, options = {}) {
        const {
            headerBg = this.palette.tableHeader,
            headerText = this.palette.tableHeaderText,
            rowAltBg = this.palette.tableRowAlt,
            borderColor = this.palette.tableBorder,
            fontSize = 8.5,
            cellPadding = 3
        } = options;

        if (!tableData || !tableData.headers || !tableData.rows) return;

        const { headers, rows } = tableData;
        const numCols = headers.length;

        // Calculate column widths based on content
        const allCells = [headers, ...rows];
        const colWidths = new Array(numCols).fill(0);

        allCells.forEach(row => {
            row.forEach((cell, colIndex) => {
                const cellText = normalizeUnicode(String(cell || ''));
                const cellWidth = this.pdf.getTextWidth(cellText) + cellPadding * 2 + 2;
                colWidths[colIndex] = Math.max(colWidths[colIndex], cellWidth);
            });
        });

        // Normalize column widths to fit
        const totalWidth = colWidths.reduce((a, b) => a + b, 0);
        const scale = totalWidth > this.contentWidth
            ? this.contentWidth / totalWidth
            : 1;

        const scaledColWidths = colWidths.map(w => Math.floor(w * scale));
        const rowHeight = fontSize + cellPadding * 2 + 2;

        // Calculate total table height
        const tableHeight = rowHeight * (rows.length + 1) + 2;

        this.ensureSpace(tableHeight + 5);

        const startY = this.cursorY;

        // Draw header row
        let x = this.marginX;
        headers.forEach((header, colIndex) => {
            this.setFillColor(headerBg);
            this.setDrawColor(borderColor);
            this.pdf.rect(x, this.cursorY, scaledColWidths[colIndex], rowHeight, 'FD');

            this.setTextColor(headerText);
            this.pdf.setFont('helvetica', 'bold');
            this.pdf.setFontSize(fontSize);
            const headerText2 = normalizeUnicode(String(header || ''));
            const truncated = this.pdf.splitTextToSize(headerText2, scaledColWidths[colIndex] - cellPadding * 2)[0];
            this.pdf.text(truncated, x + cellPadding, this.cursorY + rowHeight / 2 + fontSize / 3);

            x += scaledColWidths[colIndex];
        });

        this.cursorY += rowHeight;

        // Draw data rows
        rows.forEach((row, rowIndex) => {
            if (rowIndex % 2 === 1) {
                this.setFillColor(rowAltBg);
                this.pdf.rect(this.marginX, this.cursorY, this.contentWidth, rowHeight, 'F');
            }

            x = this.marginX;
            row.forEach((cell, colIndex) => {
                this.setDrawColor(borderColor);
                this.pdf.line(x, this.cursorY, x + scaledColWidths[colIndex], this.cursorY);
                this.pdf.line(x, this.cursorY, x, this.cursorY + rowHeight);

                this.setTextColor(this.palette.text);
                this.pdf.setFont('helvetica', 'normal');
                this.pdf.setFontSize(fontSize);
                const cellText = normalizeUnicode(String(cell || ''));
                const truncated = this.pdf.splitTextToSize(cellText, scaledColWidths[colIndex] - cellPadding * 2)[0];
                this.pdf.text(truncated, x + cellPadding, this.cursorY + rowHeight / 2 + fontSize / 3);

                x += scaledColWidths[colIndex];
            });

            // Right border of last column
            this.pdf.line(x, this.cursorY, x, this.cursorY + rowHeight);

            this.cursorY += rowHeight;
        });

        // Bottom border
        this.pdf.line(this.marginX, this.cursorY, this.marginX + this.contentWidth, this.cursorY);

        this.cursorY += 5;
        this.setTextColor(this.palette.text);
    }

    addMetricsGrid(metrics, options = {}) {
        const { cardGap = 4, cardHeight = 17 } = options;

        this.addSectionTitle('Key Metrics');

        const cardWidth = (this.contentWidth - cardGap) / 2;
        const rows = Math.ceil(metrics.length / 2);
        const totalHeight = rows * cardHeight + (rows - 1) * cardGap;
        const cardFills = ['#F8FAFC', '#F0F9FF', '#F9FAFB', '#ECFEFF'];

        this.ensureSpace(totalHeight + 2);

        metrics.forEach((item, index) => {
            const row = Math.floor(index / 2);
            const col = index % 2;
            const x = this.marginX + col * (cardWidth + cardGap);
            const y = this.cursorY + row * (cardHeight + cardGap);

            this.setFillColor(cardFills[index % cardFills.length]);
            this.setDrawColor(this.palette.border);
            this.pdf.roundedRect(x, y, cardWidth, cardHeight, 1.5, 1.5, 'FD');

            this.setTextColor(this.palette.muted);
            this.pdf.setFont('helvetica', 'bold');
            this.pdf.setFontSize(8);
            this.pdf.text(normalizeUnicode(item.label), x + 3, y + 5);

            this.setTextColor(this.palette.text);
            this.pdf.setFont('helvetica', 'normal');
            this.pdf.setFontSize(9.5);
            const valueLines = this.pdf.splitTextToSize(
                normalizeUnicode(String(item.value || 'TBD')),
                cardWidth - 6
            ).slice(0, 2);
            this.pdf.text(valueLines, x + 3, y + 10);
        });

        this.cursorY += totalHeight + 2;
    }

    addVerdictBox(verdict) {
        const style = verdict.toUpperCase().includes('GO') && !verdict.toUpperCase().includes('NO')
            ? this.palette.verdictGo
            : verdict.toUpperCase().includes('NO-GO')
                ? this.palette.verdictNoGo
                : this.palette.verdictCaution;

        this.addSectionTitle('Go / No-Go Recommendation');
        this.ensureSpace(14);

        this.setFillColor(style.fill);
        this.setDrawColor(style.border);
        this.pdf.roundedRect(this.marginX, this.cursorY, this.contentWidth, 12, 2, 2, 'FD');

        this.setTextColor(style.text);
        this.pdf.setFont('helvetica', 'bold');
        this.pdf.setFontSize(11.5);
        this.pdf.text(verdict.toUpperCase(), this.marginX + 3, this.cursorY + 7.4);

        this.cursorY += 18;
    }

    addQuestionAnswer(q, a, index) {
        this.addParagraphs(`${index + 1}. ${normalizeUnicode(q)}`, {
            fontSize: 10,
            lineHeight: 4.8,
            bold: true
        });
        this.addParagraphs(`Answer: ${normalizeUnicode(a) || 'Pending clarification'}`, {
            fontSize: 10,
            lineHeight: 4.8,
            color: a ? this.palette.muted : '#94A3B8'
        });
        this.cursorY += 2;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN PDF GENERATOR
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Generate a robust PDF from AI analysis result
 * Works consistently regardless of which AI model generated the content
 */
export const generateRobustPDF = (result, options = {}) => {
    const {
        filename = 'Report',
        title = 'Analysis Report',
        metrics = [],
        questions = [],
        answers = {},
        additionalNotes = '',
        reasoningText = ''
    } = options;

    try {
        const pdf = new jsPDF({ orientation: 'p', unit: 'mm', format: 'a4', compress: true });
        const components = new PdfComponents(pdf);

        // Normalize main analysis text
        const analysisText = normalizeForPdf(result.analysis?.analysis || '');

        // Extract tables from analysis
        const tables = extractTables(analysisText);

        // Extract and remove mermaid diagrams (they'll be handled separately)
        const mermaidDiagrams = extractMermaidDiagrams(result.analysis?.analysis || '');
        const textWithoutDiagrams = analysisText.replace(/```mermaid\n?[\s\S]*?```/gi, '\n[Architecture Diagram]\n');

        // Extract verdict
        const verdictMatch = textWithoutDiagrams.match(/Verdict:\s*\[?\s*(GO|NO-GO|PROCEED WITH CAUTION)\s*\]?/i);
        const verdict = verdictMatch ? verdictMatch[1].toUpperCase() : 'NOT SPECIFIED';

        // Split into sections
        const sections = splitIntoSections(textWithoutDiagrams);

        // Executive Summary (first paragraph(s))
        const execSummaryMatch = textWithoutDiagrams.match(/Executive Summary[\s\S]*?(?=##|\n\n|$)/i);
        let execSummaryText = execSummaryMatch
            ? execSummaryMatch[0].replace(/^#+\s*Executive Summary\s*/i, '').trim()
            : textWithoutDiagrams.split(/\n\n/)[0] || '';

        // Remaining analysis
        let remainingText = textWithoutDiagrams
            .replace(/Executive Summary[\s\S]*?(?=##|\n\n|$)/i, '')
            .replace(/^#+\s*0\.\d+\s*/gm, '');

        // Draw initial header
        components.drawHeader(title, filename);

        // Project Overview Box
        components.ensureSpace(25);
        pdf.setFillColor('#F8FAFC');
        pdf.setDrawColor(components.palette.border);
        pdf.roundedRect(components.marginX, components.cursorY, components.contentWidth, 19, 2, 2, 'FD');

        components.setTextColor(components.palette.text);
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(11);
        pdf.text('Project Overview', components.marginX + 3, components.cursorY + 6);

        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(9);
        components.setTextColor(components.palette.muted);
        const generatedAt = new Date().toLocaleString('en-IN');
        pdf.text(`Document: ${filename}`, components.marginX + 3, components.cursorY + 12);
        pdf.text(`Generated: ${generatedAt}`, components.marginX + 3, components.cursorY + 17);

        components.cursorY += 24;

        // Verdict Box
        components.addVerdictBox(verdict);

        // Executive Summary
        components.cursorY += 4;
        components.addSectionTitle('Executive Summary');
        components.addParagraphs(execSummaryText || 'Executive summary not available.', {
            fontSize: 10,
            lineHeight: 4.8
        });

        // Key Metrics
        if (metrics.length > 0) {
            components.cursorY += 2;
            components.addMetricsGrid(metrics);
        }

        // Analysis Sections with Tables
        components.addSectionTitle('Analysis');
        components.cursorY += 3;

        // Process sections - render tables in place
        const sectionText = remainingText;
        const lines = sectionText.split('\n');
        let tableBuffer = [];

        for (const line of lines) {
            const trimmed = line.trim();

            // If this is a table row
            if (trimmed.includes('|') && trimmed.split('|').filter(c => c.trim()).length >= 3) {
                tableBuffer.push(trimmed);
            } else {
                // Flush table buffer if exists
                if (tableBuffer.length > 0) {
                    const tableData = components.constructor.parseTableFromLines(tableBuffer);
                    if (tableData) {
                        components.addTable(tableData);
                    }
                    tableBuffer = [];
                }

                // Add regular text line
                if (trimmed) {
                    components.addParagraphs(normalizeUnicode(trimmed), {
                        fontSize: 10,
                        lineHeight: 4.8
                    });
                } else {
                    components.cursorY += 1;
                }
            }
        }

        // Flush remaining table
        if (tableBuffer.length > 0) {
            const tableData = components.constructor.parseTableFromLines(tableBuffer);
            if (tableData) {
                components.addTable(tableData);
            }
        }

        // Questions & Clarifications
        if (questions.length > 0) {
            components.cursorY += 2;
            components.addSectionTitle('Targeted Questions & Clarifications');
            components.cursorY += 3;

            questions.forEach((q, i) => {
                const answer = answers?.[i] || '';
                components.addQuestionAnswer(q, answer, i);
            });
        }

        // Additional Context
        if (additionalNotes) {
            components.cursorY += 2;
            components.addSectionTitle('Additional Context');
            components.addParagraphs(normalizeUnicode(additionalNotes), {
                fontSize: 10,
                lineHeight: 4.8,
                color: components.palette.muted
            });
        }

        // Reasoning Notes
        if (reasoningText) {
            components.cursorY += 2;
            components.addSectionTitle('Model Reasoning Notes');
            components.addParagraphs(normalizeUnicode(reasoningText), {
                fontSize: 9,
                lineHeight: 4.5,
                color: components.palette.muted
            });
        }

        // Add footer to all pages
        components.drawFooter();

        // Save PDF
        const safeFilename = String(filename)
            .replace(/[^a-zA-Z0-9._-]/g, '_')
            .slice(0, 80);
        pdf.save(`DSuite_Analysis_${safeFilename}.pdf`);

        return true;
    } catch (err) {
        console.error('PDF generation failed:', err);
        throw err;
    }
};

// Static method to parse table from lines
PdfComponents.parseTableFromLines = (lines) => {
    if (!lines || lines.length < 2) return null;

    const rows = [];
    let headers = null;

    for (const line of lines) {
        const cells = line.split('|')
            .map(c => c.trim())
            .filter(c => c && !/^-+$/.test(c) && !/^:+-+:+$/.test(c));

        if (cells.length === 0) continue;

        if (!headers) {
            headers = cells;
        } else {
            rows.push(cells);
        }
    }

    if (!headers || rows.length === 0) return null;

    return { headers, rows };
};

export default generateRobustPDF;