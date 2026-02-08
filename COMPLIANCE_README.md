# MCP Compliance Gateway

> Compliance governance layer for MCP server management. Built on top of [MCPHub](https://github.com/samanhappy/mcphub), extending it with compliance workflows, RBAC, and audit trails for regulated environments.

**Branch:** `feature/mcp-compliance-gateway`

---

## Quick Start (Local Development)

### Prerequisites

- Node.js 18+ (or 20+)
- pnpm (`npm install -g pnpm`)
- PostgreSQL 16 (optional — SQLite fallback for local dev)

### 1. Clone and Install

```bash
git clone <this-repo-url> MCPHub-Compliance
cd MCPHub-Compliance
git checkout feature/mcp-compliance-gateway
pnpm install
```

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
# === Server ===
PORT=3000
NODE_ENV=development

# === Database ===
# Option A: PostgreSQL (production / corporate)
# USE_DB=true
# DB_URL=postgresql://mcphub:password@localhost:5432/mcp_compliance

# Option B: SQLite via sql.js (local dev, no PostgreSQL needed)
USE_DB=false
DB_TYPE=sqlite
COMPLIANCE_DB_PATH=./compliance.sqlite

# === Auth ===
# Set to true to skip auth during local testing
# Set to false for production — requires login
# SKIP_AUTH is set in mcp_settings.json under systemConfig.routing.skipAuth

# === Smart Routing (optional) ===
SMART_ROUTING_ENABLED=false
# OPENAI_API_KEY=sk-...
```

### 3. Start Development Servers

```bash
# Start both backend (port 3000) and frontend (port 5173)
pnpm dev

# Or start them separately:
pnpm backend:dev    # Backend only — http://localhost:3000
pnpm frontend:dev   # Frontend only — http://localhost:5173 (proxies to backend)
```

### 4. Open the UI

Navigate to **http://localhost:5173** in your browser. Click **Compliance** in the sidebar.

### 5. Seed Test Data (optional)

```bash
# Register your chain server MCP servers for compliance review
curl -X POST http://localhost:3000/api/compliance/check \
  -H "Content-Type: application/json" \
  -d '{"serverId":"sec-filing-server","serverName":"SEC Filing Retrieval","mcpUrl":"https://tg40-ravenpack-agent.cfk.devfg.rbc.com/mcp/"}'

curl -X POST http://localhost:3000/api/compliance/check \
  -H "Content-Type: application/json" \
  -d '{"serverId":"earnings-call-server","serverName":"Earnings Call Analyzer","mcpUrl":"https://tg40-aiden-earnings-call-agent-v2-research.cfk.devfg.rbc.com/mcp/"}'

curl -X POST http://localhost:3000/api/compliance/check \
  -H "Content-Type: application/json" \
  -d '{"serverId":"news-retrieval-server","serverName":"News Retrieval Tool","mcpUrl":"https://tg40-ravenpack-agent.cfk.devfg.rbc.com/mcp/"}'
```

---

## Connecting to PostgreSQL (Corporate)

When you're ready to connect to your provisioned PostgreSQL instance:

1. Update `.env`:

```bash
USE_DB=true
DB_URL=postgresql://mcphub:<password>@<host>:5432/mcp_compliance
```

2. Remove or comment out the SQLite lines:

```bash
# DB_TYPE=sqlite              # remove or comment
# COMPLIANCE_DB_PATH=...      # remove or comment
```

3. Restart the server. TypeORM will auto-create the `compliance_records` and `compliance_audit_logs` tables (via `synchronize: true`).

4. Disable `skipAuth` in `mcp_settings.json` for production:

```json
{
  "systemConfig": {
    "routing": {
      "skipAuth": false
    }
  }
}
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   MCPHub Frontend                     │
│          (React + Tailwind + Vite @ :5173)           │
│                                                       │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ Servers   │  │  Compliance  │  │  Groups/Users  │ │
│  │ Page      │  │  Page (NEW)  │  │  Pages         │ │
│  └──────────┘  └──────────────┘  └────────────────┘ │
└───────────────────────┬─────────────────────────────┘
                        │ /api/*
┌───────────────────────▼─────────────────────────────┐
│                MCPHub Backend (Express @ :3000)       │
│                                                       │
│  ┌──────────────┐  ┌───────────────────────────────┐ │
│  │ Server Mgmt  │  │  Compliance Controller (NEW)  │ │
│  │ Controller   │  │  - 8 REST endpoints           │ │
│  │              │  │  - Audit logging               │ │
│  └──────────────┘  └───────────────────────────────┘ │
│                                                       │
│  ┌──────────────┐  ┌───────────────────────────────┐ │
│  │ Main DB      │  │  Compliance DB (NEW)          │ │
│  │ (PostgreSQL) │  │  (PostgreSQL or SQLite)        │ │
│  │ servers,     │  │  compliance_records,           │ │
│  │ users, etc.  │  │  compliance_audit_logs         │ │
│  └──────────────┘  └───────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## API Reference

### Control Plane — MCP Server Management (Adapters)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/adapters` | Deploy and register a new MCP server |
| `GET` | `/adapters` | List all MCP servers the user can access |
| `GET` | `/adapters/{name}` | Retrieve metadata for a specific adapter |
| `GET` | `/adapters/{name}/status` | Check the deployment status |
| `GET` | `/adapters/{name}/logs` | Access the server's running logs |
| `PUT` | `/adapters/{name}` | Update the deployment |
| `DELETE` | `/adapters/{name}` | Remove the server |

### Control Plane — Tool Registration and Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/tools` | Register and deploy a tool with MCP tool definition metadata |
| `GET` | `/tools` | List all registered tools the user can access |
| `GET` | `/tools/{name}` | Retrieve metadata and tool definition for a specific tool |
| `GET` | `/tools/{name}/status` | Check the tool deployment status |
| `GET` | `/tools/{name}/logs` | Access the tool server's running logs |
| `PUT` | `/tools/{name}` | Update a tool deployment and definition |
| `DELETE` | `/tools/{name}` | Remove a registered tool |

### Data Plane — Gateway Routing

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/adapters/{name}/mcp` | Establish a streamable HTTP connection to MCP server |

### Compliance Gateway (NEW)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/compliance/dashboard` | Dashboard stats: total, approved, pending, rejected, suspended counts |
| `GET` | `/api/compliance/servers` | List all compliance records. Filter: `?status=approved` |
| `GET` | `/api/compliance/status/{serverId}` | Get compliance status for a specific server |
| `POST` | `/api/compliance/check` | Register a server for compliance review |
| `POST` | `/api/compliance/approve/{serverId}` | Approve a server (requires `reviewer` in body) |
| `POST` | `/api/compliance/reject/{serverId}` | Reject a server (requires `reviewer`, `notes` in body) |
| `POST` | `/api/compliance/suspend/{serverId}` | Suspend a server (requires `reason` in body) |
| `GET` | `/api/compliance/audit/{serverId}` | Get audit trail for a server. Optional: `?limit=100` |

### Compliance API Examples

**Register a server for compliance review:**

```bash
curl -X POST http://localhost:3000/api/compliance/check \
  -H "Content-Type: application/json" \
  -d '{
    "serverId": "sec-filing-server",
    "serverName": "SEC Filing Retrieval",
    "mcpUrl": "https://tg40-ravenpack-agent.cfk.devfg.rbc.com/mcp/"
  }'
```

**Approve a server:**

```bash
curl -X POST http://localhost:3000/api/compliance/approve/sec-filing-server \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer": "Ramesh",
    "notes": "Passed all compliance checks. TLS verified.",
    "expiresAt": "2026-08-07T00:00:00Z"
  }'
```

**Reject a server:**

```bash
curl -X POST http://localhost:3000/api/compliance/reject/news-server \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer": "Ramesh",
    "notes": "Missing TLS certificate verification"
  }'
```

**Suspend a server:**

```bash
curl -X POST http://localhost:3000/api/compliance/suspend/market-data \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Vulnerability found in dependency chain"
  }'
```

**Get audit trail:**

```bash
curl http://localhost:3000/api/compliance/audit/sec-filing-server?limit=50
```

---

## Compliance Data Model

### compliance_records

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `serverId` | VARCHAR(255) | Unique identifier matching MCPHub server name |
| `serverName` | VARCHAR(255) | Human-readable server name |
| `mcpUrl` | TEXT | MCP endpoint URL |
| `status` | VARCHAR(50) | `pending_review`, `approved`, `rejected`, `suspended`, `conditionally_approved` |
| `complianceScore` | INT | 0-100 score from automated scanning |
| `reviewedAt` | DATETIME | When last reviewed |
| `reviewedBy` | VARCHAR(255) | Who reviewed |
| `reviewNotes` | TEXT | Reviewer's notes |
| `conditions` | TEXT | Conditions for conditional approval |
| `expiresAt` | DATETIME | When approval expires |
| `ruleResults` | JSON | Rule evaluation results from automated scanning |
| `metadata` | JSON | Additional metadata |
| `created_at` | DATETIME | Record creation timestamp |
| `updated_at` | DATETIME | Last updated timestamp |

### compliance_audit_logs

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `serverId` | VARCHAR(255) | Server this event relates to |
| `eventType` | VARCHAR(100) | `registered`, `approved`, `rejected`, `suspended`, `connection_blocked`, etc. |
| `actor` | VARCHAR(255) | Who performed the action |
| `details` | TEXT | Description of what happened |
| `previousStatus` | VARCHAR(50) | Status before the change |
| `newStatus` | VARCHAR(50) | Status after the change |
| `metadata` | JSON | Additional event data |
| `created_at` | DATETIME | Event timestamp |

---

## Files Changed (from base MCPHub)

### New Files

| File | Description |
|------|-------------|
| `src/db/complianceDataSource.ts` | Separate TypeORM data source for compliance (supports PostgreSQL + SQLite) |
| `src/db/entities/ComplianceRecord.ts` | Compliance record entity |
| `src/db/entities/ComplianceAuditLog.ts` | Immutable audit log entity |
| `src/controllers/complianceController.ts` | 8 REST API endpoints for compliance management |
| `frontend/src/pages/CompliancePage.tsx` | React compliance dashboard with stats, table, modals |

### Modified Files

| File | Change |
|------|--------|
| `src/db/entities/index.ts` | Added ComplianceRecord and ComplianceAuditLog exports |
| `src/db/connection.ts` | Added `isSqliteMode()` helper for SQLite detection |
| `src/routes/index.ts` | Added 8 compliance route registrations |
| `src/server.ts` | Added compliance DB initialization on startup |
| `frontend/src/types/index.ts` | Added TypeScript types for compliance |
| `frontend/src/App.tsx` | Added CompliancePage route at `/compliance` |
| `frontend/src/components/layout/Sidebar.tsx` | Added Compliance navigation item |
| `mcp_settings.json` | Added `skipAuth: true` for development |

---

## Roadmap

### Phase 1 — ChainServer Compliance Module (Next)
- Python `agentorchestrator/compliance/` package
- ComplianceMiddleware (priority 5) with before()/after() hooks
- Pre-flight compliance check in `MCPAdapterAgent.initialize()`
- EventBus integration for audit trail publishing
- Extended `ComponentStatus` enum: APPROVED, PENDING_REVIEW, REJECTED, SUSPENDED

### Phase 2 — RBAC and Tool Visibility
- Role field on User entity: `admin`, `compliance_reviewer`, `viewer`, `user`
- Permission middleware per compliance endpoint
- Tool listing on compliance page (pulls from MCPHub server registry)
- LDAP/AD group mapping for corporate identity integration

### Phase 3 — Automated Scanning
- Lasso Security integration for tool-level risk scanning
- Compliance scoring engine (0-100)
- Scheduled re-evaluation with ComplianceScheduler
- Expiry monitoring and auto-suspension

### Phase 4 — Kubernetes Enforcement
- OPA/Gatekeeper admission policies
- Phased rollout: monitor -> soft_enforce -> full_enforce
- Continuous monitoring dashboards

---

## License

Based on [MCPHub](https://github.com/samanhappy/mcphub) — ISC License.
