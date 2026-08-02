import { jsPDF } from 'jspdf';

/**
 * Premium Executive PDF Generator matching the Platform Utilization Briefing styling.
 * 
 * @param {Array} orgs List of organizations with users and projects
 * @param {Object} stats Overall platform stats
 * @param {String} title Main report title
 * @param {String} subtitle Report subtitle
 * @param {String} filename Saved file name
 * @param {String} dateRange Human-readable date range string
 */
export function generateSuperAdminPDF(orgs, stats, title, subtitle, filename, dateRange) {
  try {
    const doc = new jsPDF({
      orientation: 'p',
      unit: 'mm',
      format: 'a4'
    });

    const pageWidth = 210;
    const pageHeight = 297;
    const margin = 15;
    const contentWidth = pageWidth - (margin * 2);
    let cursorY = 15;

    // --- Dynamic Color System (Matching CSS Custom Properties) ---
    const colors = {
      navy950: [10, 22, 40],     // #0A1628
      navy900: [15, 32, 56],     // #0F2038
      navy800: [22, 48, 79],     // #16304F
      navy700: [31, 67, 104],    // #1F4368
      slate600: [75, 90, 110],   // #4B5A6E
      slate400: [123, 138, 158], // #7B8A9E
      slate200: [214, 220, 228], // #D6DCE4
      paper: [246, 245, 241],    // #F6F5F1
      paperCard: [255, 255, 255],// #FFFFFF
      brass: [176, 141, 79],     // #B08D4F
      brassLight: [216, 188, 133],// #D8BC85
      hairline: [220, 216, 206]  // #DCD8CE
    };

    const applyFillColor = (rgb) => doc.setFillColor(rgb[0], rgb[1], rgb[2]);
    const applyTextColor = (rgb) => doc.setTextColor(rgb[0], rgb[1], rgb[2]);
    const applyDrawColor = (rgb) => doc.setDrawColor(rgb[0], rgb[1], rgb[2]);

    const checkSpace = (heightNeeded) => {
      if (cursorY + heightNeeded > pageHeight - 22) {
        doc.addPage();
        cursorY = 22;
        drawCompactPageHeader();
      }
    };

    const drawCompactPageHeader = () => {
      // Top header line and DSUITE platform indicator
      applyFillColor(colors.navy950);
      doc.rect(margin, 10, contentWidth, 0.4, 'F');

      doc.setFont('helvetica', 'bold');
      doc.setFontSize(8);
      applyTextColor(colors.navy950);
      doc.text("DSUITE PLATFORM", margin, 8);

      doc.setFont('helvetica', 'normal');
      applyTextColor(colors.slate400);
      doc.text("EXECUTIVE PLATFORM TELEMETRY BRIEFING", margin + 35, 8);

      const dateStr = new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
      doc.text(dateStr, pageWidth - margin - doc.getTextWidth(dateStr), 8);
    };

    // --- Helper to draw Sections ---
    const drawSectionHeader = (num, secTitle, dek) => {
      checkSpace(24);
      
      // Section number in brass (Times italic/serif)
      doc.setFont('times', 'italic');
      doc.setFontSize(11);
      applyTextColor(colors.brass);
      doc.text(num, margin, cursorY);

      // Section title in Fraunces style (Times-Bold)
      doc.setFont('times', 'bold');
      doc.setFontSize(16);
      applyTextColor(colors.navy950);
      doc.text(secTitle, margin + 8, cursorY);
      cursorY += 5;

      // Section Dek (description) in slate
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(9.5);
      applyTextColor(colors.slate600);
      doc.text(dek, margin, cursorY);
      cursorY += 8;
    };

    // ───────────────────────────────────────────────────────────────────────────
    // 1. MASTHEAD (Page 1)
    // ───────────────────────────────────────────────────────────────────────────
    applyFillColor(colors.navy950);
    doc.rect(margin, cursorY, contentWidth, 62, 'F');

    // Accent line on left (Gold/Brass)
    applyFillColor(colors.brass);
    doc.rect(margin, cursorY, 2.5, 62, 'F');

    // Header label
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(10);
    doc.setTextColor(255, 255, 255);
    doc.text("DSUITE", margin + 8, cursorY + 9);

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    applyTextColor(colors.brassLight);
    const confLabel = "PREPARED FOR EXECUTIVE & CXO STAKEHOLDERS  ·  STRICTLY CONFIDENTIAL";
    doc.text(confLabel, pageWidth - margin - 8 - doc.getTextWidth(confLabel), cursorY + 9);

    // Title in serif style (Times-Bold)
    doc.setFont('times', 'bold');
    doc.setFontSize(22);
    doc.setTextColor(255, 255, 255);
    doc.text(title, margin + 8, cursorY + 22);

    // Subtitle
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9.5);
    doc.setTextColor(200, 205, 215);
    doc.text(subtitle, margin + 8, cursorY + 30);

    // Divider line inside masthead
    applyFillColor(colors.navy700);
    doc.rect(margin + 8, cursorY + 38, contentWidth - 16, 0.3, 'F');

    // Metadata column layouts
    const metaY = cursorY + 45;
    const colW = (contentWidth - 16) / 4;

    const uniqueUsers = new Set();
    orgs.forEach(o => {
      (o.users || []).forEach(u => {
        if (u.email) uniqueUsers.add(u.email.toLowerCase());
      });
    });

    const metaItems = [
      { label: "REPORTING WINDOW", val: dateRange || "All-Time to Date" },
      { label: "PREPARED", val: new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }) },
      { label: "SOURCE", val: "DSuite Platform Billing Ledger" },
      { label: "SCOPE", val: `${orgs.length} Orgs · ${uniqueUsers.size} Users` }
    ];

    metaItems.forEach((item, idx) => {
      const colX = margin + 8 + (idx * colW);
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(6.5);
      applyTextColor(colors.brassLight);
      doc.text(item.label, colX, metaY);

      doc.setFont('helvetica', 'medium');
      doc.setFontSize(8.5);
      doc.setTextColor(255, 255, 255);
      doc.text(item.val, colX, metaY + 5);
    });

    cursorY += 76;

    // ───────────────────────────────────────────────────────────────────────────
    // 2. EXECUTIVE SUMMARY
    // ───────────────────────────────────────────────────────────────────────────
    drawSectionHeader("01", "Executive Summary", "All-time totals across the platform.");

    const kpiW = (contentWidth - 9) / 4;
    const kpiH = 26;

    const summaryCards = [
      { label: "Total Spend", val: `$${(stats?.platform_billing || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, note: "Across all organizations, all-time" },
      { label: "Tokens Consumed", val: (stats?.ai_tokens_consumed || 0).toLocaleString(), note: "AI tokens, all-time" },
      { label: "Active Organizations", val: String(stats?.total_organizations || orgs.length), note: "All-time" },
      { label: "Active Users", val: String(uniqueUsers.size), note: "Across both organizations" }
    ];

    summaryCards.forEach((card, idx) => {
      const cardX = margin + (idx * (kpiW + 3));

      // Draw background card (White with hairline border)
      applyFillColor(colors.paperCard);
      applyDrawColor(colors.hairline);
      doc.roundedRect(cardX, cursorY, kpiW, kpiH, 0.5, 0.5, 'FD');

      // Label (slate-400 monospace styled)
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(7.5);
      applyTextColor(colors.slate600);
      doc.text(card.label.toUpperCase(), cardX + 4, cursorY + 6);

      // Value in Times-Bold (Fraunces style)
      doc.setFont('times', 'bold');
      doc.setFontSize(15);
      applyTextColor(colors.navy950);
      doc.text(card.val, cardX + 4, cursorY + 14);

      // Notes
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(6.5);
      applyTextColor(colors.slate600);
      doc.text(doc.splitTextToSize(card.note, kpiW - 8), cardX + 4, cursorY + 20);
    });

    cursorY += kpiH + 14;

    // ───────────────────────────────────────────────────────────────────────────
    // 3. COST ATTRIBUTION DETAIL
    // ───────────────────────────────────────────────────────────────────────────
    drawSectionHeader("02", "Cost Attribution Detail", "Spend and token usage rolled up by organization, broken down by project, and attributed to each user.");

    orgs.forEach((o) => {
      checkSpace(34);

      // Render Organization Box Header
      applyFillColor(colors.paperCard);
      applyDrawColor(colors.hairline);
      doc.roundedRect(margin, cursorY, contentWidth, 18, 0.5, 0.5, 'FD');

      // Left bar in Gold/Brass
      applyFillColor(colors.brass);
      doc.rect(margin, cursorY, 1.5, 18, 'F');

      // Organization Name (Serif font)
      doc.setFont('times', 'bold');
      doc.setFontSize(12.5);
      applyTextColor(colors.navy950);
      const orgNameStr = o.organization_name;
      doc.text(orgNameStr, margin + 5, cursorY + 6.5);

      // Draw organization tags next to name
      const orgTags = o.organization_tags || [];
      if (orgTags.length > 0) {
        let tagCursorX = margin + 5 + doc.getTextWidth(orgNameStr) + 5;
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(6.5);
        
        orgTags.forEach(t => {
          const tagText = String(t).toUpperCase();
          const tagW = doc.getTextWidth(tagText) + 4;
          
          // Draw tag pill background (light purple/indigo tint)
          doc.setFillColor(235, 235, 250);
          doc.roundedRect(tagCursorX, cursorY + 2.5, tagW, 4.5, 0.4, 0.4, 'F');
          
          // Draw tag text (indigo color)
          doc.setTextColor(79, 70, 229);
          doc.text(tagText, tagCursorX + 2, cursorY + 5.7);
          
          tagCursorX += tagW + 2;
        });
      }

      // Initialize the projects map from the master projects list of the organization
      const projectsMap = {};
      (o.projects || []).forEach(p => {
        const pTok = p.project_token || 'direct_api';
        projectsMap[pTok] = {
          project_token: pTok,
          project_name: p.project_name || (pTok === 'direct_api' ? 'Direct API / Custom Workspace' : `Project (${pTok})`),
          total_tokens: p.total_tokens || 0,
          total_cost: p.total_cost || 0,
          users: []
        };
      });

      // Ensure 'direct_api' is present in projectsMap
      if (!projectsMap['direct_api']) {
        projectsMap['direct_api'] = {
          project_token: 'direct_api',
          project_name: 'Direct API / Custom Workspace',
          total_tokens: 0,
          total_cost: 0,
          users: []
        };
      }

      // Map users' token/cost usage to their respective projects
      (o.users || []).forEach(u => {
        (u.projects || []).forEach(p => {
          const pTok = p.project_token || 'direct_api';
          if (!projectsMap[pTok]) {
            projectsMap[pTok] = {
              project_token: pTok,
              project_name: p.project_name || `Project (${pTok})`,
              total_tokens: p.total_tokens || 0,
              total_cost: p.total_cost || 0,
              users: []
            };
          }
          
          if (!projectsMap[pTok].users.some(pu => pu.email === u.email)) {
            projectsMap[pTok].users.push({
              email: u.email,
              first_name: u.first_name,
              last_name: u.last_name,
              is_org_admin: u.is_org_admin,
              is_super_admin: u.is_super_admin,
              tokens: p.total_tokens || 0,
              cost: p.total_cost || 0
            });
          }
        });
      });

      const projectsList = Object.values(projectsMap);

      // Organization Metadata
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(8.5);
      applyTextColor(colors.slate600);
      doc.text(`${o.max_agent_capacity} Agent Capacity  ·  ${(o.users || []).length} Members  ·  ${o.total_onboarded_agents} Active Agents  ·  ${projectsList.length} Projects`, margin + 5, cursorY + 12);

      // Right Side: Org Total Spend
      doc.setFont('times', 'bold');
      doc.setFontSize(13);
      applyTextColor(colors.navy950);
      const orgCostStr = `$${(o.total_cost || 0).toFixed(4)}`;
      doc.text(orgCostStr, pageWidth - margin - 5 - doc.getTextWidth(orgCostStr), cursorY + 7.5);

      doc.setFont('helvetica', 'bold');
      doc.setFontSize(6.5);
      applyTextColor(colors.slate400);
      doc.text("TOTAL ORG SPEND", pageWidth - margin - 5 - doc.getTextWidth("TOTAL ORG SPEND"), cursorY + 12);

      cursorY += 21;

      // Draw Projects Block
      if (projectsList.length === 0) {
        checkSpace(12);
        applyFillColor(colors.paperCard);
        applyDrawColor(colors.hairline);
        doc.rect(margin, cursorY, contentWidth, 10, 'FD');
        doc.setFont('helvetica', 'italic');
        doc.setFontSize(8.5);
        applyTextColor(colors.slate400);
        doc.text("No project activity recorded for this organization", margin + 6, cursorY + 6.5);
        cursorY += 13;
      } else {
        projectsList.forEach((proj) => {
          checkSpace(28);

          // Project Head Bar (Paper style colored header bar)
          applyFillColor(colors.paper);
          applyDrawColor(colors.hairline);
          doc.rect(margin, cursorY, contentWidth, 9, 'FD');

          // Project Name
          doc.setFont('helvetica', 'bold');
          doc.setFontSize(9);
          applyTextColor(colors.navy900);
          doc.text(proj.project_name, margin + 4, cursorY + 5.8);

          // Project Token Pill (Courier style)
          doc.setFont('courier', 'bold');
          doc.setFontSize(7.5);
          applyTextColor(colors.slate600);
          const tokStr = `[${proj.project_token}]`;
          doc.text(tokStr, margin + 8 + doc.getTextWidth(proj.project_name), cursorY + 5.8);

          // Project tags next to token
          const matchingProj = (o.projects || []).find(op => op.project_token === proj.project_token);
          const pTags = matchingProj ? (matchingProj.tags || []) : [];
          if (pTags.length > 0) {
            let tagCursorX = margin + 8 + doc.getTextWidth(proj.project_name) + doc.getTextWidth(tokStr) + 4;
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(6.5);
            
            pTags.forEach(t => {
              const tagText = String(t).toUpperCase();
              const tagW = doc.getTextWidth(tagText) + 3;
              
              // Draw tag pill background (light indigo/blue tint)
              doc.setFillColor(230, 242, 255);
              doc.roundedRect(tagCursorX, cursorY + 2.2, tagW, 4.2, 0.4, 0.4, 'F');
              
              // Draw tag text (blue color)
              doc.setTextColor(30, 64, 175);
              doc.text(tagText, tagCursorX + 1.5, cursorY + 5.2);
              
              tagCursorX += tagW + 2;
            });
          }

          // Project Total (Right aligned)
          doc.setFont('helvetica', 'normal');
          doc.setFontSize(8.5);
          applyTextColor(colors.navy700);
          const pCostStr = `$${(proj.total_cost || 0).toFixed(4)}`;
          const pTokensStr = `${(proj.total_tokens || 0).toLocaleString()} tokens   ·   `;
          
          doc.setFont('helvetica', 'bold');
          doc.text(pCostStr, pageWidth - margin - 4 - doc.getTextWidth(pCostStr), cursorY + 5.8);
          doc.setFont('helvetica', 'normal');
          doc.text(pTokensStr, pageWidth - margin - 4 - doc.getTextWidth(pCostStr) - doc.getTextWidth(pTokensStr), cursorY + 5.8);

          cursorY += 9;

          if (proj.users.length === 0) {
            checkSpace(12);
            applyFillColor(colors.paperCard);
            applyDrawColor(colors.hairline);
            doc.rect(margin, cursorY, contentWidth, 8, 'FD');
            doc.setFont('helvetica', 'italic');
            doc.setFontSize(8);
            applyTextColor(colors.slate400);
            doc.text("No user usage telemetry recorded for this project", margin + 6, cursorY + 5.5);
            cursorY += 10;
          } else {
            // Draw Users Table Headers
            doc.setFillColor(255, 255, 255);
            doc.rect(margin, cursorY, contentWidth, 7, 'F');
            
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(7);
            applyTextColor(colors.slate400);
            doc.text("USER", margin + 6, cursorY + 5);
            doc.text("ROLE", margin + 95, cursorY + 5);
            doc.text("TOKENS", margin + 130, cursorY + 5);
            doc.text("COST", margin + 160, cursorY + 5);

            cursorY += 7;

            // Draw User Rows
            proj.users.forEach((pu, puIdx) => {
              checkSpace(10);
              
              // Draw alternating row background
              if (puIdx % 2 === 1) {
                doc.setFillColor(250, 250, 248);
                doc.rect(margin, cursorY, contentWidth, 8.5, 'F');
              }

              // Bottom border row
              applyDrawColor(colors.hairline);
              doc.line(margin, cursorY + 8.5, pageWidth - margin, cursorY + 8.5);

              // User Email
              doc.setFont('helvetica', 'normal');
              doc.setFontSize(8.5);
              applyTextColor(colors.navy900);
              doc.text(pu.email, margin + 6, cursorY + 5.5);

              // Role pill background
              const roleStr = pu.is_super_admin ? 'Super Admin' : pu.is_org_admin ? 'Org Admin' : 'Member';
              doc.setFillColor(220, 224, 230);
              doc.roundedRect(margin + 94, cursorY + 1.8, 20, 4.5, 0.4, 0.4, 'F');
              doc.setFont('helvetica', 'bold');
              doc.setFontSize(6.5);
              applyTextColor(colors.navy800);
              doc.text(roleStr, margin + 104 - (doc.getTextWidth(roleStr) / 2), cursorY + 5.0);

              // Tokens (Right-aligned)
              doc.setFont('helvetica', 'normal');
              doc.setFontSize(8);
              applyTextColor(colors.slate600);
              const tokVal = (pu.tokens || 0).toLocaleString();
              doc.text(tokVal, margin + 145 - doc.getTextWidth(tokVal), cursorY + 5.5);

              // Cost (Right-aligned)
              doc.setFont('helvetica', 'bold');
              applyTextColor(colors.navy900);
              const costVal = `$${(pu.cost || 0).toFixed(4)}`;
              doc.text(costVal, margin + 175 - doc.getTextWidth(costVal), cursorY + 5.5);

              cursorY += 8.5;
            });
            cursorY += 4; // Spacer after table
          }
        });
      }
      cursorY += 8; // Extra spacing between Orgs
    });

    cursorY += 4;

    // ───────────────────────────────────────────────────────────────────────────
    // 4. CUMULATIVE SPEND BY USER
    // ───────────────────────────────────────────────────────────────────────────
    drawSectionHeader("03", "Cumulative Spend by User", "Total cost and tokens per user, aggregated across every project and organization they belong to. Ranked highest to lowest.");

    // Aggregate user rankings
    const rankingsMap = {};
    orgs.forEach(o => {
      (o.users || []).forEach(u => {
        const key = u.email.toLowerCase();
        if (!rankingsMap[key]) {
          rankingsMap[key] = {
            email: u.email,
            tokens: 0,
            cost: 0.0
          };
        }
        rankingsMap[key].tokens += u.ai_tokens || 0;
        rankingsMap[key].cost += u.total_cost || 0;
      });
    });

    const rankingsList = Object.values(rankingsMap).sort((a, b) => b.cost - a.cost);
    const maxUserCost = rankingsList[0]?.cost || 1.0;
    const totalPlatformSpend = stats?.platform_billing || rankingsList.reduce((s, u) => s + u.cost, 0) || 1.0;

    checkSpace(rankingsList.length * 15 + 10);

    // Rank outer border card container
    applyFillColor(colors.paperCard);
    applyDrawColor(colors.hairline);
    doc.roundedRect(margin, cursorY, contentWidth, rankingsList.length * 14.5 + 2, 0.5, 0.5, 'FD');

    rankingsList.forEach((ru, rIdx) => {
      const rowY = cursorY + 1 + (rIdx * 14.5);

      // Underline row
      if (rIdx < rankingsList.length - 1) {
        applyDrawColor(colors.hairline);
        doc.line(margin + 4, rowY + 14.5, pageWidth - margin - 4, rowY + 14.5);
      }

      // Rank Position
      doc.setFont('times', 'bold');
      doc.setFontSize(13);
      applyTextColor(colors.brass);
      doc.text(String(rIdx + 1), margin + 6, rowY + 9.5);

      // Email
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(9);
      applyTextColor(colors.navy950);
      doc.text(ru.email, margin + 14, rowY + 5.5);

      // Dynamic Progress bar variables
      const barMaxW = 75; // mm width of bar
      const barFillW = maxUserCost > 0 ? (ru.cost / maxUserCost) * barMaxW : 0;

      // Draw Progress Bar Track
      applyFillColor(colors.slate200);
      doc.roundedRect(margin + 14, rowY + 8, barMaxW, 1.8, 0.3, 0.3, 'F');

      // Draw Progress Bar Fill
      if (barFillW > 0) {
        applyFillColor(rIdx === 0 ? colors.brass : colors.navy800);
        doc.roundedRect(margin + 14, rowY + 8, barFillW, 1.8, 0.3, 0.3, 'F');
      }

      // Token Details (under tokens column)
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(8.5);
      applyTextColor(colors.slate600);
      const tokenStr = `${(ru.tokens || 0).toLocaleString()} tokens`;
      doc.text(tokenStr, margin + 98, rowY + 6.0);

      // Share Percentage
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(7.5);
      applyTextColor(colors.slate400);
      const pct = totalPlatformSpend > 0 ? ((ru.cost / totalPlatformSpend) * 100).toFixed(1) : "0.0";
      doc.text(`${pct}% of total spend`, margin + 98, rowY + 10.5);

      // Spend Cost (Right aligned)
      doc.setFont('courier', 'bold');
      doc.setFontSize(11);
      applyTextColor(colors.navy950);
      const costStr = `$${(ru.cost || 0).toFixed(4)}`;
      doc.text(costStr, pageWidth - margin - 8 - doc.getTextWidth(costStr), rowY + 9.0);
    });

    cursorY += rankingsList.length * 14.5 + 10;

    // ───────────────────────────────────────────────────────────────────────────
    // 5. FOOTER & COMPACT HEADER MULTI-PASS
    // ───────────────────────────────────────────────────────────────────────────
    const totalPages = doc.internal.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
      doc.setPage(i);

      if (i > 1) {
        drawCompactPageHeader();
      }

      // Draw footer divider line
      applyFillColor(colors.hairline);
      doc.rect(margin, pageHeight - 14, contentWidth, 0.3, 'F');

      doc.setFont('helvetica', 'normal');
      doc.setFontSize(7.5);
      applyTextColor(colors.slate400);
      doc.text("DSUITE PLATFORM  ·  EXECUTIVE BRIEFING", margin, pageHeight - 9);

      const pageNumStr = `Page ${i} of ${totalPages}`;
      doc.text(pageNumStr, pageWidth - margin - doc.getTextWidth(pageNumStr), pageHeight - 9);
    }

    doc.save(filename);
  } catch (err) {
    console.error('Failed to generate Premium Executive PDF Report:', err);
    alert('PDF Generation failed: ' + err.message);
  }
}
