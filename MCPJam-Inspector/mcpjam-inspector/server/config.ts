/**
 * Server configuration constants
 */

import dotenv from "dotenv";
import { existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

// Load env vars early so they are available for config constants.
// In ES modules, static imports are hoisted, so dotenv must be loaded
// here rather than in the main entry file.
const __cfgDir = dirname(fileURLToPath(import.meta.url));
const __rootDir = resolve(__cfgDir, "..");
for (const f of [".env.development", ".env.local", ".env"]) {
  const p = resolve(__rootDir, f);
  if (existsSync(p)) {
    dotenv.config({ path: p });
    break;
  }
}

// Server port - can be overridden via environment variable
export const SERVER_PORT = process.env.SERVER_PORT
  ? parseInt(process.env.SERVER_PORT, 10)
  : 6274;

// Server hostname
export const SERVER_HOSTNAME =
  process.env.ENVIRONMENT === "dev" ? "localhost" : "127.0.0.1";

// Local server address for tunneling
export const LOCAL_SERVER_ADDR = `http://localhost:${SERVER_PORT}`;

// CORS origins
export const CORS_ORIGINS = [
  "http://localhost:5173", // Vite dev server
  "http://localhost:8080", // Electron renderer dev server
  `http://localhost:${SERVER_PORT}`, // Hono server
  `http://127.0.0.1:${SERVER_PORT}`, // Hono server production
  "https://staging.app.mcpjam.com", // Hosted deployment
];

// Hosted mode for cloud deployments (Railway, etc.)
// When enabled: disables STDIO transport (security: prevents RCE) and requires HTTPS
// Uses VITE_ prefix so the same variable works for both server and client build
export const HOSTED_MODE = process.env.VITE_MCPJAM_HOSTED_MODE === "true";

// Allowed hosts for token delivery in hosted mode (comma-separated)
// These hosts will be allowed to receive session tokens in addition to localhost
export const ALLOWED_HOSTS = process.env.MCPJAM_ALLOWED_HOSTS
  ? process.env.MCPJAM_ALLOWED_HOSTS.split(",").map((h) =>
      h.trim().toLowerCase(),
    )
  : [];
