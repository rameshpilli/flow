import { useState, useEffect, useCallback, useMemo } from "react";
import { getInternalLlmConfig } from "@/lib/internal-llm-config";

export interface ProviderTokens {
  anthropic: string;
  anthropicBaseUrl: string;
  azure: string;
  azureBaseUrl: string;
  openai: string;
  openaiBaseUrl: string;
  deepseek: string;
  google: string;
  mistral: string;
  xai: string;
  ollama: string;
  ollamaBaseUrl: string;
  litellm: string;
  litellmBaseUrl: string;
  litellmModelAlias: string;
  openrouter: string;
  openRouterSelectedModels: string[];
}

export interface useAiProviderKeysReturn {
  tokens: ProviderTokens;
  setToken: (provider: keyof ProviderTokens, token: string) => void;
  clearToken: (provider: keyof ProviderTokens) => void;
  clearAllTokens: () => void;
  hasToken: (provider: keyof ProviderTokens) => boolean;
  getToken: (provider: keyof ProviderTokens) => string;
  getOllamaBaseUrl: () => string;
  setOllamaBaseUrl: (url: string) => void;
  getLiteLLMBaseUrl: () => string;
  setLiteLLMBaseUrl: (url: string) => void;
  getLiteLLMModelAlias: () => string;
  setLiteLLMModelAlias: (alias: string) => void;
  getOpenRouterSelectedModels: () => string[];
  setOpenRouterSelectedModels: (models: string[]) => void;
  getAzureBaseUrl: () => string;
  setAzureBaseUrl: (url: string) => void;
  getAnthropicBaseUrl: () => string;
  setAnthropicBaseUrl: (url: string) => void;
  getOpenAIBaseUrl: () => string;
  setOpenAIBaseUrl: (url: string) => void;
}

const STORAGE_KEY = "mcp-inspector-provider-tokens";

const baseDefaultTokens: ProviderTokens = {
  anthropic: "",
  anthropicBaseUrl: "",
  azure: "",
  azureBaseUrl: "",
  openai: "",
  openaiBaseUrl: "",
  deepseek: "",
  google: "",
  mistral: "",
  xai: "",
  ollama: "local", // Ollama runs locally, no API key needed
  ollamaBaseUrl: "http://127.0.0.1:11434/api",
  litellm: "", // LiteLLM API key (optional, depends on proxy setup)
  litellmBaseUrl: "http://localhost:4000", // Default LiteLLM proxy URL
  litellmModelAlias: "", // Model name/alias to use with LiteLLM
  openrouter: "",
  openRouterSelectedModels: [],
};

export function useAiProviderKeys(): useAiProviderKeysReturn {
  const internalConfig = useMemo(() => getInternalLlmConfig(), []);
  const internalModelsAlias = internalConfig?.models.join(",") ?? "";
  const internalBaseUrl = internalConfig?.baseUrl ?? "";

  const [tokens, setTokens] = useState<ProviderTokens>(baseDefaultTokens);
  const [isInitialized, setIsInitialized] = useState(false);

  // Load tokens from localStorage on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsedTokens = JSON.parse(stored) as ProviderTokens;
          setTokens(parsedTokens);
        }
      } catch (error) {
        console.warn(
          "Failed to load provider tokens from localStorage:",
          error,
        );
      }
      if (internalConfig && internalConfig.enabled) {
        setTokens((prev) => ({
          ...prev,
          litellmBaseUrl: prev.litellmBaseUrl || internalBaseUrl,
          litellmModelAlias: prev.litellmModelAlias || internalModelsAlias,
        }));
      }
      setIsInitialized(true);
    }
  }, [internalConfig, internalBaseUrl, internalModelsAlias]);

  // Save tokens to localStorage whenever they change
  useEffect(() => {
    if (isInitialized && typeof window !== "undefined") {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
      } catch (error) {
        console.warn("Failed to save provider tokens to localStorage:", error);
      }
    }
  }, [tokens, isInitialized]);

  const setToken = useCallback(
    (provider: keyof ProviderTokens, token: string) => {
      setTokens((prev) => ({
        ...prev,
        [provider]: token,
      }));
    },
    [],
  );

  const clearToken = useCallback((provider: keyof ProviderTokens) => {
    setTokens((prev) => ({
      ...prev,
      [provider]: "",
    }));
  }, []);

  const clearAllTokens = useCallback(() => {
    setTokens(baseDefaultTokens);
  }, []);

  const hasToken = useCallback(
    (provider: keyof ProviderTokens) => {
      const value = tokens[provider];
      if (provider === "openrouter") {
        // For OpenRouter, check both API key and selected models
        return (
          Boolean(tokens.openrouter?.trim()) &&
          tokens.openRouterSelectedModels.length > 0
        );
      }
      if (Array.isArray(value)) {
        return value.length > 0;
      }
      return Boolean(value?.trim());
    },
    [tokens],
  );

  const getToken = useCallback(
    (provider: keyof ProviderTokens) => {
      const value = tokens[provider];
      if (Array.isArray(value)) {
        return value.join(", ");
      }
      return value || "";
    },
    [tokens],
  );

  const getOllamaBaseUrl = useCallback(() => {
    return tokens.ollamaBaseUrl || baseDefaultTokens.ollamaBaseUrl;
  }, [tokens.ollamaBaseUrl]);

  const setOllamaBaseUrl = useCallback((url: string) => {
    setTokens((prev) => ({
      ...prev,
      ollamaBaseUrl: url,
    }));
  }, []);

  const getLiteLLMBaseUrl = useCallback(() => {
    return (
      tokens.litellmBaseUrl ||
      internalBaseUrl ||
      baseDefaultTokens.litellmBaseUrl
    );
  }, [tokens.litellmBaseUrl, internalBaseUrl]);

  const setLiteLLMBaseUrl = useCallback((url: string) => {
    setTokens((prev) => ({
      ...prev,
      litellmBaseUrl: url,
    }));
  }, []);

  const getLiteLLMModelAlias = useCallback(() => {
    return (
      tokens.litellmModelAlias ||
      internalModelsAlias ||
      baseDefaultTokens.litellmModelAlias
    );
  }, [tokens.litellmModelAlias, internalModelsAlias]);

  const setLiteLLMModelAlias = useCallback((alias: string) => {
    setTokens((prev) => ({
      ...prev,
      litellmModelAlias: alias,
    }));
  }, []);

  const getAzureBaseUrl = useCallback(() => {
    return tokens.azureBaseUrl || baseDefaultTokens.azureBaseUrl;
  }, [tokens.azureBaseUrl]);

  const setAzureBaseUrl = useCallback((url: string) => {
    setTokens((prev) => ({
      ...prev,
      azureBaseUrl: url,
    }));
  }, []);

  const getOpenRouterSelectedModels = useCallback(() => {
    return (
      tokens.openRouterSelectedModels ||
      baseDefaultTokens.openRouterSelectedModels
    );
  }, [tokens.openRouterSelectedModels]);

  const setOpenRouterSelectedModels = useCallback((models: string[]) => {
    setTokens((prev) => ({
      ...prev,
      openRouterSelectedModels: models,
    }));
  }, []);

  const getAnthropicBaseUrl = useCallback(() => {
    return tokens.anthropicBaseUrl || "";
  }, [tokens.anthropicBaseUrl]);

  const setAnthropicBaseUrl = useCallback((url: string) => {
    setTokens((prev) => ({
      ...prev,
      anthropicBaseUrl: url,
    }));
  }, []);

  const getOpenAIBaseUrl = useCallback(() => {
    return tokens.openaiBaseUrl || "";
  }, [tokens.openaiBaseUrl]);

  const setOpenAIBaseUrl = useCallback((url: string) => {
    setTokens((prev) => ({
      ...prev,
      openaiBaseUrl: url,
    }));
  }, []);

  return {
    tokens,
    setToken,
    clearToken,
    clearAllTokens,
    hasToken,
    getToken,
    getOllamaBaseUrl,
    setOllamaBaseUrl,
    getLiteLLMBaseUrl,
    setLiteLLMBaseUrl,
    getLiteLLMModelAlias,
    setLiteLLMModelAlias,
    getOpenRouterSelectedModels,
    setOpenRouterSelectedModels,
    getAzureBaseUrl,
    setAzureBaseUrl,
    getAnthropicBaseUrl,
    setAnthropicBaseUrl,
    getOpenAIBaseUrl,
    setOpenAIBaseUrl,
  };
}
