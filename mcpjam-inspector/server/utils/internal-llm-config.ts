type TokenState = {
  token: string;
  expiresAt: number;
};

export type InternalLlmUiConfig = {
  enabled: true;
  baseUrl: string;
  models: string[];
};

const normalizeGatewayBaseUrl = (rawUrl: string): string => {
  return rawUrl.replace(/\/chat\/completions\/?$/, "");
};

const parseModels = (models?: string): string[] => {
  if (!models) return [];
  return models
    .split(",")
    .map((m) => m.trim())
    .filter((m) => m.length > 0);
};

const applyTlsSettings = () => {
  if (process.env.LLM_VERIFY_SSL?.toLowerCase() === "false") {
    process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
  }
};

export const getInternalLlmUiConfig = (): InternalLlmUiConfig | null => {
  const serverUrl = process.env.LLM_SERVER_URL || process.env.LLM_GATEWAY_URL;
  const models = parseModels(process.env.LLM_MODELS);
  if (!serverUrl || models.length === 0) return null;

  return {
    enabled: true,
    baseUrl: normalizeGatewayBaseUrl(serverUrl),
    models,
  };
};

let cachedToken: TokenState | null = null;

const fetchOAuthToken = async (): Promise<string | null> => {
  const oauthEndpoint = process.env.LLM_OAUTH_ENDPOINT;
  const clientId = process.env.LLM_CLIENT_ID;
  const clientSecret = process.env.LLM_CLIENT_SECRET;
  if (!oauthEndpoint || !clientId || !clientSecret) {
    return null;
  }

  if (cachedToken && Date.now() < cachedToken.expiresAt) {
    return cachedToken.token;
  }

  applyTlsSettings();

  const body = new URLSearchParams({
    grant_type: process.env.LLM_OAUTH_GRANT_TYPE || "client_credentials",
    client_id: clientId,
    client_secret: clientSecret,
    scope: process.env.LLM_OAUTH_SCOPE || "read",
  });

  const response = await fetch(oauthEndpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body.toString(),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `OAuth token request failed (${response.status}): ${errorText}`,
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
};

export const resolveInternalLlmToken = async (): Promise<string | null> => {
  const apiKey = process.env.LLM_API_KEY;
  if (apiKey) return apiKey;
  return fetchOAuthToken();
};

export const getInternalLlmBaseUrl = (): string | null => {
  const serverUrl = process.env.LLM_SERVER_URL || process.env.LLM_GATEWAY_URL;
  if (!serverUrl) return null;
  return normalizeGatewayBaseUrl(serverUrl);
};
