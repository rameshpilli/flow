---
name: jira-sprint-report
description: "Generate Sprint Summary PowerPoint presentations from JIRA data. Creates dashboard-style reports with issue details, velocity trends, and sprint summaries."
---

# JIRA Sprint Report Skill

Generate professional Sprint Summary PowerPoint presentations from JIRA sprint data.

## Quick Start

1. **Prepare your data** in JSON format (see `templates/sample-data.json`)
2. **Run the generator**:
   ```bash
   node scripts/generate-report.js <data.json> <output.pptx>
   ```

## Usage

### Option 1: Provide JSON Data File
```bash
# User provides a JSON file with sprint data
node scripts/generate-report.js sprint-data.json Sprint_Report.pptx
```

### Option 2: Generate from JIRA Export
```bash
# Convert JIRA CSV export to JSON first, then generate
node scripts/generate-report.js converted-data.json Sprint_Report.pptx
```

### Option 3: Direct JIRA API (if Atlassian MCP connected)
Claude can query JIRA directly, transform to JSON, then run the script.

## Data Format

The script expects a JSON file with this structure:

```json
{
  "sprint": {
    "name": "Sprint 2024-03",
    "startDate": "Jan 06, 2025",
    "endDate": "Jan 17, 2025",
    "teamName": "Phoenix Engineering",
    "teamSize": 20
  },
  "metrics": {
    "completed": { "points": 148, "issues": 42 },
    "blocked": { "issues": 3 },
    "spillover": { "points": 18, "issues": 6 },
    "avgVelocity": 142
  },
  "velocity": {
    "current": [0, 28, 58, 92, 118, 148],
    "previous": [0, 22, 48, 78, 105, 132],
    "labels": ["Day 0", "Day 2", "Day 4", "Day 6", "Day 8", "Day 10"]
  },
  "issues": [
    {
      "key": "PHX-301",
      "type": "Story",
      "summary": "Implement user authentication API",
      "estimate": 5,
      "assignee": "Sarah Chen",
      "status": "Done",
      "daysOver": -1
    }
  ],
  "nextSprint": {
    "name": "2024-04",
    "dates": "Jan 20 - Jan 31, 2025",
    "duration": "10 working days",
    "plannedCapacity": 165,
    "spillover": 18,
    "available": 147,
    "goal": "Complete Payment Integration..."
  }
}
```

## Output

The script generates a PowerPoint with:

| Slide | Content |
|-------|---------|
| 1 | Title + Sprint dates + Team size |
| 2 | Dashboard: KPIs + Velocity Chart + Status Pie |
| 3-N | Issue Details Table (20 issues/page) |
| Last | Summary: Achievements + Blockers + Next Sprint |

## Issue Fields

| Field | Required | Description |
|-------|----------|-------------|
| `key` | Yes | JIRA ticket number (e.g., "PHX-301") |
| `type` | Yes | "Story" or "Bug" only |
| `summary` | Yes | Issue title |
| `estimate` | Yes | Story points |
| `assignee` | Yes | Person's display name |
| `status` | Yes | "Done", "In Progress", or "Blocked" |
| `daysOver` | No | Days over/under estimate (null if not done) |
| `blocker` | No | Blocker reason (for blocked items) |

## Days Over/Under

```
daysOver = actual_days - estimated_days

-2  → Finished 2 days early (green)
 0  → On time (blue)
+3  → 3 days over estimate (red)
null → Not yet completed (shows "-")
```

## Color Scheme

- **Primary**: Dark teal (#1a5f7a)
- **Success/Done/Early**: Green (#22c55e)
- **Warning/In Progress**: Amber (#f59e0b)
- **Danger/Blocked/Late**: Red (#ef4444)
- **Story type**: Indigo (#6366f1)
- **Bug type**: Red (#ef4444)

## JIRA Field Mapping

| JIRA Field | JSON Field |
|------------|------------|
| `issue.key` | `key` |
| `issue.fields.issuetype.name` | `type` |
| `issue.fields.summary` | `summary` |
| `issue.fields.customfield_10016` | `estimate` |
| `issue.fields.assignee.displayName` | `assignee` |
| `issue.fields.status.name` | `status` |
| Calculated from resolution | `daysOver` |

## Files

- `SKILL.md` - This documentation
- `scripts/generate-report.js` - Main generator script
- `templates/sample-data.json` - Example data structure
