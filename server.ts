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

type LlmGatewayConfig = {
  serverUrl: string;
  modelName: string;
  temperature: number;
  maxTokens: number;
  topP: number | null;
  apiKey?: string;
  oauthEndpoint?: string;
  clientId?: string;
  clientSecret?: string;
  oauthScope: string;
  oauthGrantType: string;
};

type TokenState = {
  token: string;
  expiresAt: number;
};

const llmConfig: LlmGatewayConfig = {
  serverUrl: process.env.LLM_SERVER_URL || process.env.LLM_GATEWAY_URL || "",
  modelName: process.env.LLM_MODEL_NAME || "gpt-4",
  temperature: Number.parseFloat(process.env.LLM_TEMPERATURE || "0.2"),
  maxTokens: Number.parseInt(process.env.LLM_MAX_TOKENS || "4096", 10),
  topP: Number.isFinite(Number.parseFloat(process.env.LLM_TOP_P || ""))
    ? Number.parseFloat(process.env.LLM_TOP_P || "0")
    : null,
  apiKey: process.env.LLM_API_KEY || undefined,
  oauthEndpoint: process.env.LLM_OAUTH_ENDPOINT || undefined,
  clientId: process.env.LLM_CLIENT_ID || undefined,
  clientSecret: process.env.LLM_CLIENT_SECRET || undefined,
  oauthScope: process.env.LLM_OAUTH_SCOPE || "read",
  oauthGrantType: process.env.LLM_OAUTH_GRANT_TYPE || "client_credentials",
};

let cachedToken: TokenState | null = null;

function ensureTlsSettings() {
  if (process.env.LLM_VERIFY_SSL?.toLowerCase() === "false") {
    process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
    console.warn(
      "[MCPJam Dummy Server] LLM_VERIFY_SSL=false; TLS verification is disabled."
    );
  }
}

function llmConfigured(): boolean {
  const hasServer = Boolean(llmConfig.serverUrl);
  const hasAuth =
    Boolean(llmConfig.apiKey) ||
    Boolean(
      llmConfig.oauthEndpoint &&
        llmConfig.clientId &&
        llmConfig.clientSecret
    );
  return hasServer && hasAuth;
}

function formatConfigError(): string {
  return [
    "LLM Gateway is not configured.",
    "Set LLM_SERVER_URL (or LLM_GATEWAY_URL) and one of:",
    "- LLM_API_KEY",
    "- or LLM_OAUTH_ENDPOINT + LLM_CLIENT_ID + LLM_CLIENT_SECRET",
  ].join("\n");
}

async function fetchOAuthToken(): Promise<string> {
  if (!llmConfig.oauthEndpoint || !llmConfig.clientId || !llmConfig.clientSecret) {
    throw new Error("OAuth credentials are not configured");
  }

  if (cachedToken && Date.now() < cachedToken.expiresAt) {
    return cachedToken.token;
  }

  const body = new URLSearchParams({
    grant_type: llmConfig.oauthGrantType,
    client_id: llmConfig.clientId,
    client_secret: llmConfig.clientSecret,
    scope: llmConfig.oauthScope,
  });

  const response = await fetch(llmConfig.oauthEndpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body.toString(),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `OAuth token request failed (${response.status}): ${errorText}`
    );
  }

  const data = (await response.json()) as {
    access_token?: string;
    expires_in?: number;
  };

  if (!data.access_token) {
    throw new Error("OAuth token response missing access_token");
  }

  const expiresIn = Number.isFinite(data.expires_in)
    ? Number(data.expires_in)
    : 3600;
  const bufferSeconds = Math.min(60, Math.max(5, Math.floor(expiresIn * 0.2)));
  const effectiveExpiry = Math.max(expiresIn - bufferSeconds, 5);

  cachedToken = {
    token: data.access_token,
    expiresAt: Date.now() + effectiveExpiry * 1000,
  };

  return data.access_token;
}

async function getAuthToken(): Promise<string> {
  if (llmConfig.apiKey) {
    return llmConfig.apiKey;
  }
  return fetchOAuthToken();
}

async function callLlmGateway(params: {
  prompt: string;
  system?: string;
  model?: string;
  temperature?: number;
  maxTokens?: number;
  topP?: number;
}): Promise<{ text: string; raw: unknown }> {
  if (!llmConfigured()) {
    throw new Error(formatConfigError());
  }

  ensureTlsSettings();

  const token = await getAuthToken();

  const messages: Array<{ role: "system" | "user"; content: string }> = [];
  if (params.system) {
    messages.push({ role: "system", content: params.system });
  }
  messages.push({ role: "user", content: params.prompt });

  const payload: Record<string, unknown> = {
    model: params.model || llmConfig.modelName,
    messages,
    max_tokens: params.maxTokens ?? llmConfig.maxTokens,
  };

  const temperature = params.temperature ?? llmConfig.temperature;
  if (Number.isFinite(temperature)) {
    payload.temperature = temperature;
  }

  const topP = params.topP ?? llmConfig.topP;
  if (topP !== null && Number.isFinite(topP)) {
    payload.top_p = topP;
  }

  const response = await fetch(llmConfig.serverUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `LLM gateway request failed (${response.status}): ${errorText}`
    );
  }

  const data = await response.json();
  const text =
    data?.choices?.[0]?.message?.content ??
    data?.choices?.[0]?.text ??
    JSON.stringify(data);

  return { text, raw: data };
}

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
    "llm-chat",
    {
      title: "LLM Gateway Chat",
      description:
        "Send a prompt to your internal LLM gateway (env-configured).",
      inputSchema: {
        type: "object",
        properties: {
          prompt: {
            type: "string",
            description: "User prompt for the model.",
          },
          system: {
            type: "string",
            description: "Optional system message.",
          },
          model: {
            type: "string",
            description: "Override model name (optional).",
          },
          temperature: {
            type: "number",
            description: "Override temperature (optional).",
          },
          max_tokens: {
            type: "number",
            description: "Override max tokens (optional).",
          },
          top_p: {
            type: "number",
            description: "Override top_p (optional).",
          },
        },
        required: ["prompt"],
      },
    },
    async (request): Promise<CallToolResult> => {
      try {
        const args = (request?.params?.arguments ?? {}) as {
          prompt?: string;
          system?: string;
          model?: string;
          temperature?: number;
          max_tokens?: number;
          top_p?: number;
        };

        if (!args.prompt) {
          return {
            content: [
              {
                type: "text",
                text: "Missing required field: prompt",
              },
            ],
          };
        }

        const result = await callLlmGateway({
          prompt: args.prompt,
          system: args.system,
          model: args.model,
          temperature: args.temperature,
          maxTokens: args.max_tokens,
          topP: args.top_p,
        });

        return {
          content: [
            {
              type: "text",
              text: result.text,
            },
          ],
        };
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Unknown error";
        return {
          content: [
            {
              type: "text",
              text: `LLM gateway error: ${message}`,
            },
          ],
        };
      }
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
