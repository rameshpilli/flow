import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import type { CallToolResult, ReadResourceResult } from "@modelcontextprotocol/sdk/types.js";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  registerAppTool,
  registerAppResource,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST_DIR = path.join(__dirname, "dist");

export function createServer(): McpServer {
  const server = new McpServer({
    name: "Dummy MCP App Server",
    version: "1.0.0",
  });

  const resourceUri = "ui://dummy/dummy-app.html";

  registerAppResource(
    server,
    resourceUri,
    resourceUri,
    { mimeType: RESOURCE_MIME_TYPE },
    async (): Promise<ReadResourceResult> => {
      const html = await fs.readFile(path.join(DIST_DIR, "dummy-app.html"), "utf-8");
      return {
        contents: [{ uri: resourceUri, mimeType: RESOURCE_MIME_TYPE, text: html }],
      };
    }
  );

  registerAppTool(
    server,
    "show-dashboard",
    {
      title: "Show Dashboard",
      description: "Display an interactive dashboard widget",
      inputSchema: {},
      _meta: {
        ui: { resourceUri },
      },
    },
    async (): Promise<CallToolResult> => {
      return {
        content: [{ type: "text", text: "Dashboard loaded successfully!" }],
      };
    }
  );

  server.registerTool(
    "get-status",
    {
      title: "Get System Status",
      description: "Get the current system status",
      inputSchema: {},
    },
    async (): Promise<CallToolResult> => {
      return {
        content: [
          {
            type: "text",
            text: `System Status Report:
- MCPJam Server: Running ✅
- Database Connection: Active ✅
- API Response Time: 45ms
- Memory Usage: 128MB / 512MB
- Uptime: 2 hours 34 minutes`,
          },
        ],
      };
    }
  );

  return server;
}

async function main() {
  const server = createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("[MCPJam Dummy Server] Server started and listening on STDIO");
}

main().catch((e) => {
  console.error("[MCPJam Dummy Server] Fatal error:", e);
  process.exit(1);
});
