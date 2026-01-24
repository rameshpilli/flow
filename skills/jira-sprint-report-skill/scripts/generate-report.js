#!/usr/bin/env node
/**
 * JIRA Sprint Report Generator
 * Generates a PowerPoint presentation from sprint data JSON
 *
 * Usage: node generate-report.js <input.json> [output.pptx] [--template <template.pptx>]
 *
 * Template Support:
 * - Pass --template to use a branded PowerPoint template as the base
 * - The template's master slides and backgrounds will be applied
 */

const fs = require('fs');
const path = require('path');
const pptxgen = require('pptxgenjs');

// Color palette
const C = {
  primary: "1a5f7a",
  primaryDark: "0d3d4d",
  success: "22c55e",
  warning: "f59e0b",
  danger: "ef4444",
  info: "3b82f6",
  purple: "8b5cf6",
  surface: "f1f5f9",
  white: "ffffff",
  dark: "1e293b",
  muted: "64748b",
  mutedLight: "94a3b8",
  story: "6366f1",
  bug: "ef4444",
  rowAlt: "f8fafc",
  // Template-specific colors (can be overridden)
  templateBg: "f5f5f0",
  templateAccent: "b5b5a0"
};

// Table column widths (sum = 9.6)
const COL_WIDTHS = [0.9, 0.7, 4.0, 0.5, 1.7, 0.9, 0.9];
const ISSUES_PER_PAGE = 20;

/**
 * Define custom slide masters for branded templates
 */
function defineSlideMasters(pptx, templateConfig) {
  const cfg = templateConfig || {};

  // Master 1: Title slide with geometric background
  pptx.defineSlideMaster({
    title: "TITLE_SLIDE",
    background: { color: cfg.bgColor || C.templateBg },
    objects: [
      // Geometric lines pattern (similar to uploaded image)
      { line: { x: 0.5, y: 0.3, w: 4, h: 0, line: { color: cfg.accentColor || C.templateAccent, width: 0.5, transparency: 60 } } },
      { line: { x: 1, y: 0.8, w: 5, h: 0, line: { color: cfg.accentColor || C.templateAccent, width: 0.5, transparency: 60 } } },
      { line: { x: 0.3, y: 1.5, w: 3.5, h: 0, line: { color: cfg.accentColor || C.templateAccent, width: 0.5, transparency: 60 } } },
      // Footer branding
      { text: { text: cfg.footerText || "XYZ – PIP ALPHA", options: { x: 7.5, y: 5.2, w: 2.3, h: 0.3, fontSize: 10, fontFace: "Arial", color: C.dark, align: "right" } } }
    ]
  });

  // Master 2: Content slide with subtle background
  pptx.defineSlideMaster({
    title: "CONTENT_SLIDE",
    background: { color: cfg.bgColor || C.templateBg },
    objects: [
      // Subtle geometric accent
      { line: { x: 0.2, y: 0.1, w: 2, h: 0, line: { color: cfg.accentColor || C.templateAccent, width: 0.5, transparency: 70 } } },
      { line: { x: 0.5, y: 0.25, w: 1.5, h: 0, line: { color: cfg.accentColor || C.templateAccent, width: 0.5, transparency: 70 } } },
      // Footer
      { text: { text: cfg.footerText || "XYZ – PIP ALPHA", options: { x: 7.5, y: 5.2, w: 2.3, h: 0.3, fontSize: 10, fontFace: "Arial", color: C.dark, align: "right" } } }
    ]
  });

  // Master 3: Dashboard slide
  pptx.defineSlideMaster({
    title: "DASHBOARD_SLIDE",
    background: { color: cfg.bgColor || C.templateBg },
    objects: [
      // Footer
      { text: { text: cfg.footerText || "XYZ – PIP ALPHA", options: { x: 7.5, y: 5.2, w: 2.3, h: 0.3, fontSize: 10, fontFace: "Arial", color: C.dark, align: "right" } } }
    ]
  });

  return {
    title: "TITLE_SLIDE",
    content: "CONTENT_SLIDE",
    dashboard: "DASHBOARD_SLIDE"
  };
}

function createTitleSlide(pptx, data, masters) {
  const slide = masters ? pptx.addSlide({ masterName: masters.title }) : pptx.addSlide();

  if (!masters) {
    slide.background = { color: C.primary };
    // Gradient overlay
    slide.addShape(pptx.shapes.RECTANGLE, {
      x: 0, y: 0, w: 10, h: 5.63,
      fill: { type: "solid", color: C.primaryDark, transparency: 30 }
    });
  }

  // Title - adjust colors based on whether using template
  const titleColor = masters ? C.dark : C.white;
  const subtitleColor = masters ? C.muted : C.mutedLight;

  slide.addText(data.sprint.name, {
    x: 0.5, y: 1.8, w: 9, h: 0.8,
    fontSize: 48, fontFace: "Arial", bold: true, color: titleColor, align: "center"
  });

  slide.addText("Summary Report", {
    x: 0.5, y: 2.6, w: 9, h: 0.5,
    fontSize: 20, fontFace: "Arial", color: subtitleColor, align: "center"
  });

  // Info cards
  const cards = [
    { label: "Release Start", value: data.sprint.startDate },
    { label: "Release End", value: data.sprint.endDate },
    { label: "Team Size", value: `${data.sprint.teamSize} Members` }
  ];
  const cardW = 2, cardH = 0.8, cardGap = 0.3, cardY = 3.4;
  const startX = (10 - (3 * cardW + 2 * cardGap)) / 2;

  cards.forEach((card, i) => {
    const x = startX + i * (cardW + cardGap);
    slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
      x, y: cardY, w: cardW, h: cardH,
      fill: { color: masters ? C.white : C.white, transparency: masters ? 0 : 85 },
      rectRadius: 0.1,
      line: masters ? { color: C.templateAccent, width: 0.5 } : null
    });
    slide.addText(card.label, {
      x, y: cardY + 0.08, w: cardW, h: 0.25,
      fontSize: 9, fontFace: "Arial", color: C.muted, align: "center"
    });
    slide.addText(card.value, {
      x, y: cardY + 0.35, w: cardW, h: 0.35,
      fontSize: 14, fontFace: "Arial", bold: true, color: masters ? C.dark : C.white, align: "center"
    });
  });

  // Team name
  slide.addText(data.sprint.teamName || "Engineering Team", {
    x: 0.5, y: 4.5, w: 9, h: 0.4,
    fontSize: 12, fontFace: "Arial", color: subtitleColor, align: "center"
  });
}

function createDashboardSlide(pptx, data, masters) {
  const slide = masters ? pptx.addSlide({ masterName: masters.dashboard }) : pptx.addSlide();

  if (!masters) {
    slide.background = { color: C.surface };
  }

  // Header
  slide.addShape(pptx.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.55, fill: { color: C.primary } });
  slide.addText(`${data.sprint.name} Dashboard`, {
    x: 0.3, y: 0.12, w: 5, h: 0.35,
    fontSize: 14, fontFace: "Arial", bold: true, color: C.white
  });

  // Completion badge
  const totalIssues = data.metrics.completed.issues + data.metrics.spillover.issues;
  const completionRate = Math.round((data.metrics.completed.issues / totalIssues) * 100);
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x: 8, y: 0.1, w: 1.8, h: 0.35,
    fill: { color: C.white, transparency: 85 }, rectRadius: 0.05
  });
  slide.addText(`${completionRate}% Complete`, {
    x: 8, y: 0.12, w: 1.8, h: 0.32,
    fontSize: 10, fontFace: "Arial", bold: true, color: C.success, align: "center"
  });

  // KPI Cards
  const kpis = [
    { label: "COMPLETED", value: data.metrics.completed.points, unit: "pts", sub: `${data.metrics.completed.issues} issues`, color: C.success },
    { label: "BLOCKED", value: data.metrics.blocked.issues, unit: "issues", sub: "Needs attention", color: C.danger, subColor: C.danger },
    { label: "SPILLOVER", value: data.metrics.spillover.points, unit: "pts", sub: `${data.metrics.spillover.issues} issues`, color: C.warning },
    { label: "AVG VELOCITY", value: data.metrics.avgVelocity, unit: "pts", sub: "Last 5 sprints", color: C.purple }
  ];

  const kpiY = 0.7, kpiH = 1.1, kpiW = 2.3, kpiGap = 0.15, kpiStartX = 0.2;
  kpis.forEach((kpi, i) => {
    const x = kpiStartX + i * (kpiW + kpiGap);
    slide.addShape(pptx.shapes.RECTANGLE, { x, y: kpiY, w: kpiW, h: kpiH, fill: { color: C.white } });
    slide.addShape(pptx.shapes.RECTANGLE, { x, y: kpiY, w: 0.06, h: kpiH, fill: { color: kpi.color } });
    slide.addText(kpi.label, { x: x + 0.15, y: kpiY + 0.1, w: kpiW - 0.25, h: 0.22, fontSize: 9, fontFace: "Arial", color: C.muted });
    slide.addText(String(kpi.value), { x: x + 0.15, y: kpiY + 0.35, w: 1.4, h: 0.5, fontSize: 28, fontFace: "Arial", bold: true, color: C.dark });
    slide.addText(kpi.unit, { x: x + 1.4, y: kpiY + 0.52, w: 0.8, h: 0.3, fontSize: 11, fontFace: "Arial", color: C.muted });
    slide.addText(kpi.sub, { x: x + 0.15, y: kpiY + 0.85, w: kpiW - 0.25, h: 0.2, fontSize: 9, fontFace: "Arial", color: kpi.subColor || C.mutedLight });
  });

  // Charts
  const chartY = 2.0, chartH = 3.0;

  // Velocity chart
  slide.addShape(pptx.shapes.RECTANGLE, { x: 0.2, y: chartY, w: 5.8, h: chartH, fill: { color: C.white } });
  slide.addText("Velocity Comparison: Current vs Previous Sprint", {
    x: 0.35, y: chartY + 0.12, w: 5.5, h: 0.28,
    fontSize: 11, fontFace: "Arial", bold: true, color: C.dark
  });

  const currentTotal = data.velocity.current[data.velocity.current.length - 1];
  const prevTotal = data.velocity.previous[data.velocity.previous.length - 1];
  slide.addChart(pptx.charts.LINE, [
    { name: `Current Sprint (${currentTotal} pts)`, labels: data.velocity.labels, values: data.velocity.current },
    { name: `Previous Sprint (${prevTotal} pts)`, labels: data.velocity.labels, values: data.velocity.previous }
  ], {
    x: 0.3, y: chartY + 0.5, w: 5.6, h: 2.3,
    lineSize: 3, showMarkers: true, markerSize: 6,
    chartColors: [C.success, C.muted],
    showLegend: true, legendPos: "b", legendFontSize: 9,
    valAxisMinVal: 0, valAxisMajorUnit: 40,
    catAxisLabelFontSize: 9, valAxisLabelFontSize: 9,
    showValAxisTitle: true, valAxisTitle: "Story Points", valAxisTitleFontSize: 9
  });

  // Status pie
  slide.addShape(pptx.shapes.RECTANGLE, { x: 6.15, y: chartY, w: 3.65, h: chartH, fill: { color: C.white } });
  slide.addText("Status Distribution", {
    x: 6.3, y: chartY + 0.12, w: 3.35, h: 0.28,
    fontSize: 11, fontFace: "Arial", bold: true, color: C.dark
  });

  const statusCounts = { Done: 0, "In Progress": 0, Blocked: 0 };
  data.issues.forEach(i => { if (statusCounts[i.status] !== undefined) statusCounts[i.status]++; });

  slide.addChart(pptx.charts.PIE, [{
    name: "Status",
    labels: [`Done (${statusCounts.Done})`, `In Progress (${statusCounts["In Progress"]})`, `Blocked (${statusCounts.Blocked})`],
    values: [statusCounts.Done, statusCounts["In Progress"], statusCounts.Blocked]
  }], {
    x: 6.2, y: chartY + 0.5, w: 3.55, h: 2.3,
    showPercent: true, showLegend: true, legendPos: "b", legendFontSize: 9,
    chartColors: [C.success, C.warning, C.danger]
  });
}

function createIssueSlide(pptx, issues, pageNum, totalPages, storyCount, bugCount, masters) {
  const slide = masters ? pptx.addSlide({ masterName: masters.content }) : pptx.addSlide();

  if (!masters) {
    slide.background = { color: C.surface };
  }

  // Header
  slide.addShape(pptx.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.5, fill: { color: C.primary } });
  slide.addText(`Sprint Issues: Stories & Bugs (${pageNum}/${totalPages})`, {
    x: 0.3, y: 0.1, w: 5, h: 0.32,
    fontSize: 13, fontFace: "Arial", bold: true, color: C.white
  });

  // Badges
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, { x: 7.0, y: 0.08, w: 1.3, h: 0.32, fill: { color: C.story }, rectRadius: 0.05 });
  slide.addText(`${storyCount} Stories`, { x: 7.0, y: 0.1, w: 1.3, h: 0.3, fontSize: 9, fontFace: "Arial", bold: true, color: C.white, align: "center" });
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, { x: 8.45, y: 0.08, w: 1.3, h: 0.32, fill: { color: C.bug }, rectRadius: 0.05 });
  slide.addText(`${bugCount} Bugs`, { x: 8.45, y: 0.1, w: 1.3, h: 0.3, fontSize: 9, fontFace: "Arial", bold: true, color: C.white, align: "center" });

  // Table header
  const tableY = 0.6, rowH = 0.23;
  const header = [
    { text: "Ticket", options: { fill: C.primaryDark, color: C.white, bold: true, fontSize: 9, align: "center" } },
    { text: "Type", options: { fill: C.primaryDark, color: C.white, bold: true, fontSize: 9, align: "center" } },
    { text: "Summary", options: { fill: C.primaryDark, color: C.white, bold: true, fontSize: 9 } },
    { text: "Est", options: { fill: C.primaryDark, color: C.white, bold: true, fontSize: 9, align: "center" } },
    { text: "Assignee", options: { fill: C.primaryDark, color: C.white, bold: true, fontSize: 9 } },
    { text: "Status", options: { fill: C.primaryDark, color: C.white, bold: true, fontSize: 9, align: "center" } },
    { text: "Days +/-", options: { fill: C.primaryDark, color: C.white, bold: true, fontSize: 9, align: "center" } }
  ];

  const rows = [header];
  issues.forEach((issue, idx) => {
    const rowFill = idx % 2 === 0 ? C.rowAlt : C.white;
    const typeColor = issue.type === "Story" ? C.story : C.bug;
    let statusColor = C.success;
    if (issue.status === "In Progress") statusColor = C.warning;
    if (issue.status === "Blocked") statusColor = C.danger;

    let daysText = "-", daysColor = C.muted;
    if (issue.daysOver !== null && issue.daysOver !== undefined) {
      if (issue.daysOver < 0) { daysText = `${issue.daysOver}d`; daysColor = C.success; }
      else if (issue.daysOver === 0) { daysText = "0d"; daysColor = C.info; }
      else { daysText = `+${issue.daysOver}d`; daysColor = C.danger; }
    }

    rows.push([
      { text: issue.key, options: { fill: rowFill, fontSize: 8, color: C.dark, align: "center" } },
      { text: issue.type, options: { fill: rowFill, fontSize: 8, color: typeColor, bold: true, align: "center" } },
      { text: issue.summary, options: { fill: rowFill, fontSize: 8, color: C.dark } },
      { text: `${issue.estimate}`, options: { fill: rowFill, fontSize: 8, color: C.dark, align: "center" } },
      { text: issue.assignee, options: { fill: rowFill, fontSize: 8, color: C.muted } },
      { text: issue.status, options: { fill: rowFill, fontSize: 8, color: statusColor, bold: true, align: "center" } },
      { text: daysText, options: { fill: rowFill, fontSize: 8, color: daysColor, bold: true, align: "center" } }
    ]);
  });

  slide.addTable(rows, {
    x: 0.2, y: tableY, w: 9.6,
    fontFace: "Arial", border: { pt: 0.5, color: "e2e8f0" },
    rowH: rowH, colW: COL_WIDTHS, valign: "middle"
  });

  // Legend on first page
  if (pageNum === 1) {
    const legendY = tableY + (issues.length + 1) * rowH + 0.15;
    slide.addText("Days +/-:", { x: 0.3, y: legendY, w: 0.6, h: 0.2, fontSize: 8, fontFace: "Arial", bold: true, color: C.dark });
    slide.addText("-2d = 2 days early", { x: 0.95, y: legendY, w: 1.3, h: 0.2, fontSize: 8, fontFace: "Arial", color: C.success });
    slide.addText("0d = on time", { x: 2.35, y: legendY, w: 1, h: 0.2, fontSize: 8, fontFace: "Arial", color: C.info });
    slide.addText("+3d = 3 days over", { x: 3.45, y: legendY, w: 1.4, h: 0.2, fontSize: 8, fontFace: "Arial", color: C.danger });
  }
}

function createSummarySlide(pptx, data, masters) {
  const slide = masters ? pptx.addSlide({ masterName: masters.content }) : pptx.addSlide();

  if (!masters) {
    slide.background = { color: C.surface };
  }

  // Header
  slide.addShape(pptx.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.5, fill: { color: C.primary } });
  slide.addText("Summary & Next Sprint", { x: 0.3, y: 0.1, w: 6, h: 0.32, fontSize: 13, fontFace: "Arial", bold: true, color: C.white });

  const leftW = 5.8;

  // Key Achievements
  slide.addShape(pptx.shapes.RECTANGLE, { x: 0.2, y: 0.6, w: leftW, h: 2.4, fill: { color: C.white } });
  slide.addShape(pptx.shapes.RECTANGLE, { x: 0.2, y: 0.6, w: 0.06, h: 2.4, fill: { color: C.success } });
  slide.addText("✅ Key Achievements", { x: 0.35, y: 0.68, w: leftW - 0.3, h: 0.25, fontSize: 12, fontFace: "Arial", bold: true, color: C.dark });

  (data.achievements || []).slice(0, 5).forEach((a, i) => {
    slide.addText(`•  ${a}`, { x: 0.4, y: 1.0 + i * 0.36, w: leftW - 0.4, h: 0.34, fontSize: 10, fontFace: "Arial", color: C.dark, valign: "top" });
  });

  // Blockers
  const blockers = data.issues.filter(i => i.status === "Blocked");
  slide.addShape(pptx.shapes.RECTANGLE, { x: 0.2, y: 3.15, w: leftW, h: 1.85, fill: { color: C.white } });
  slide.addShape(pptx.shapes.RECTANGLE, { x: 0.2, y: 3.15, w: 0.06, h: 1.85, fill: { color: C.danger } });
  slide.addText("🚫 Current Blockers", { x: 0.35, y: 3.23, w: leftW - 0.3, h: 0.25, fontSize: 12, fontFace: "Arial", bold: true, color: C.dark });

  blockers.forEach((issue, i) => {
    slide.addText(`${issue.key}: ${issue.summary}`, { x: 0.4, y: 3.58 + i * 0.45, w: leftW - 0.5, h: 0.2, fontSize: 10, fontFace: "Arial", bold: true, color: C.dark });
    slide.addText(`Blocker: ${issue.blocker || "Not specified"}`, { x: 0.4, y: 3.8 + i * 0.45, w: leftW - 0.5, h: 0.18, fontSize: 9, fontFace: "Arial", color: C.danger });
  });

  // Next Sprint card
  const rightX = 6.15, rightW = 3.65;
  const ns = data.nextSprint || {};

  slide.addShape(pptx.shapes.RECTANGLE, { x: rightX, y: 0.6, w: rightW, h: 4.4, fill: { color: C.primary } });
  slide.addText("📅 Next Sprint", { x: rightX + 0.2, y: 0.75, w: rightW - 0.4, h: 0.3, fontSize: 14, fontFace: "Arial", bold: true, color: C.white });
  slide.addText(ns.name || "TBD", { x: rightX + 0.2, y: 1.1, w: rightW - 0.4, h: 0.4, fontSize: 28, fontFace: "Arial", bold: true, color: C.white });

  slide.addShape(pptx.shapes.RECTANGLE, { x: rightX + 0.2, y: 1.6, w: rightW - 0.4, h: 0.02, fill: { color: C.mutedLight, transparency: 50 } });

  const info = [
    { label: "Dates", value: ns.dates || "TBD" },
    { label: "Duration", value: ns.duration || "TBD" },
    { label: "Team Size", value: `${data.sprint.teamSize} members` },
    { label: "Planned Capacity", value: `${ns.plannedCapacity || 0} story points` },
    { label: "Spillover", value: `${ns.spillover || 0} pts`, color: C.warning },
    { label: "Available for New Work", value: `${ns.available || 0} pts`, color: C.success }
  ];

  info.forEach((item, i) => {
    slide.addText(item.label, { x: rightX + 0.2, y: 1.8 + i * 0.38, w: rightW - 0.4, h: 0.2, fontSize: 9, fontFace: "Arial", color: C.mutedLight });
    slide.addText(item.value, { x: rightX + 0.2, y: 2.0 + i * 0.38, w: rightW - 0.4, h: 0.22, fontSize: 11, fontFace: "Arial", bold: true, color: item.color || C.white });
  });

  slide.addShape(pptx.shapes.RECTANGLE, { x: rightX + 0.2, y: 4.15, w: rightW - 0.4, h: 0.02, fill: { color: C.mutedLight, transparency: 50 } });
  slide.addText("Sprint Goal", { x: rightX + 0.2, y: 4.3, w: rightW - 0.4, h: 0.2, fontSize: 9, fontFace: "Arial", color: C.mutedLight });
  slide.addText(ns.goal || "TBD", { x: rightX + 0.2, y: 4.55, w: rightW - 0.4, h: 0.6, fontSize: 10, fontFace: "Arial", color: C.white, valign: "top" });
}

/**
 * Load template configuration from JSON file or use defaults
 */
function loadTemplateConfig(templatePath) {
  // If a template config JSON is provided, load it
  if (templatePath && templatePath.endsWith('.json')) {
    try {
      return JSON.parse(fs.readFileSync(templatePath, 'utf8'));
    } catch (e) {
      console.warn(`Warning: Could not load template config: ${e.message}`);
    }
  }

  // Default template configuration matching the uploaded image style
  return {
    bgColor: "f5f5f0",           // Light cream/beige background
    accentColor: "b5b5a0",       // Subtle greenish-gray for lines
    footerText: "XYZ – PIP ALPHA",
    useGeometricPattern: true
  };
}

function generateReport(data, outputPath, templateConfig) {
  const pptx = new pptxgen();
  pptx.layout = "LAYOUT_16x9";
  pptx.title = `${data.sprint.name} Summary Report`;
  pptx.author = data.sprint.teamName || "Engineering Team";

  // Define slide masters if using template
  let masters = null;
  if (templateConfig) {
    masters = defineSlideMasters(pptx, templateConfig);
    console.log(`  Using template: ${templateConfig.footerText || 'Custom'}`);
  }

  // Slide 1: Title
  createTitleSlide(pptx, data, masters);

  // Slide 2: Dashboard
  createDashboardSlide(pptx, data, masters);

  // Slides 3-N: Issues
  const sortedIssues = [...data.issues].sort((a, b) => {
    const statusOrder = { "Done": 0, "In Progress": 1, "Blocked": 2 };
    if (statusOrder[a.status] !== statusOrder[b.status]) return statusOrder[a.status] - statusOrder[b.status];
    const typeOrder = { "Story": 0, "Bug": 1 };
    return typeOrder[a.type] - typeOrder[b.type];
  });

  const storyCount = data.issues.filter(i => i.type === "Story").length;
  const bugCount = data.issues.filter(i => i.type === "Bug").length;
  const totalPages = Math.ceil(sortedIssues.length / ISSUES_PER_PAGE);

  for (let page = 0; page < totalPages; page++) {
    const start = page * ISSUES_PER_PAGE;
    const pageIssues = sortedIssues.slice(start, start + ISSUES_PER_PAGE);
    createIssueSlide(pptx, pageIssues, page + 1, totalPages, storyCount, bugCount, masters);
  }

  // Last slide: Summary
  createSummarySlide(pptx, data, masters);

  // Save
  return pptx.writeFile({ fileName: outputPath });
}

// Main
async function main() {
  const args = process.argv.slice(2);

  // Parse arguments
  let inputPath = null;
  let outputPath = null;
  let templatePath = null;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--template' && args[i + 1]) {
      templatePath = args[++i];
    } else if (!inputPath) {
      inputPath = args[i];
    } else if (!outputPath) {
      outputPath = args[i];
    }
  }

  if (!inputPath) {
    console.log("JIRA Sprint Report Generator");
    console.log("============================");
    console.log("\nUsage: node generate-report.js <input.json> [output.pptx] [--template <config.json>]");
    console.log("\nOptions:");
    console.log("  --template <config.json>  Use a branded template configuration");
    console.log("\nTemplate config format (JSON):");
    console.log("  {");
    console.log('    "bgColor": "f5f5f0",');
    console.log('    "accentColor": "b5b5a0",');
    console.log('    "footerText": "XYZ – PIP ALPHA"');
    console.log("  }");
    console.log("\nExamples:");
    console.log("  node generate-report.js sprint-data.json");
    console.log("  node generate-report.js sprint-data.json Report.pptx --template brand.json");
    process.exit(1);
  }

  outputPath = outputPath || inputPath.replace(/\.json$/i, "_Report.pptx");

  if (!fs.existsSync(inputPath)) {
    console.error(`Error: Input file not found: ${inputPath}`);
    process.exit(1);
  }

  // Load template config if specified
  let templateConfig = null;
  if (templatePath) {
    templateConfig = loadTemplateConfig(templatePath);
  }

  console.log(`Reading data from: ${inputPath}`);
  const data = JSON.parse(fs.readFileSync(inputPath, 'utf8'));

  console.log(`Generating report...`);
  console.log(`  Sprint: ${data.sprint.name}`);
  console.log(`  Team: ${data.sprint.teamName} (${data.sprint.teamSize} members)`);
  console.log(`  Issues: ${data.issues.length} (${data.issues.filter(i => i.type === "Story").length} Stories, ${data.issues.filter(i => i.type === "Bug").length} Bugs)`);

  await generateReport(data, outputPath, templateConfig);

  console.log(`\n✅ Report saved: ${outputPath}`);
  console.log(`   Total slides: ${2 + Math.ceil(data.issues.length / ISSUES_PER_PAGE) + 1}`);
}

main().catch(err => {
  console.error("Error:", err.message);
  process.exit(1);
});
