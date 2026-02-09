export type InternalLlmConfig = {
  enabled: boolean;
  baseUrl: string;
  models: string[];
};

declare global {
  interface Window {
    MCPJAM_INTERNAL_LLM_CONFIG?: InternalLlmConfig;
  }
}

export const getInternalLlmConfig = (): InternalLlmConfig | null => {
  if (typeof window === "undefined") return null;

  // 1. Check for server-injected config (production mode)
  const config = window.MCPJAM_INTERNAL_LLM_CONFIG;
  if (config?.enabled) {
    return {
      enabled: true,
      baseUrl: config.baseUrl || "",
      models: Array.isArray(config.models) ? config.models : [],
    };
  }

  // 2. Fallback: read from VITE_ env vars (development mode)
  const baseUrl = (import.meta.env.VITE_LLM_BASE_URL as string | undefined)
    || (import.meta.env.VITE_LLM_SERVER_URL as string | undefined)
    || "";
  const modelsRaw = (import.meta.env.VITE_LLM_MODELS as string | undefined) || "";
  const models = modelsRaw
    .split(",")
    .map((m: string) => m.trim())
    .filter((m: string) => m.length > 0);

  if (baseUrl && models.length > 0) {
    return { enabled: true, baseUrl, models };
  }

  return null;
};

export const isInternalLlmEnabled = (): boolean => {
  return Boolean(getInternalLlmConfig());
};
