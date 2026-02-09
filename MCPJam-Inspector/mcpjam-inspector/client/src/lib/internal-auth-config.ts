export type InternalAuthUser = {
  id?: string;
  email?: string;
  firstName?: string;
  lastName?: string;
  name?: string;
  profilePictureUrl?: string;
  imageUrl?: string;
  avatar?: string;
};

export type InternalAuthConfig = {
  enabled: boolean;
  convexAuthToken?: string;
  user?: InternalAuthUser;
};

declare global {
  interface Window {
    MCPJAM_INTERNAL_AUTH_CONFIG?: InternalAuthConfig;
  }
}

function normalizeEnvValue(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

export function getInternalAuthConfig(): InternalAuthConfig | null {
  if (typeof window !== "undefined" && window.MCPJAM_INTERNAL_AUTH_CONFIG) {
    return window.MCPJAM_INTERNAL_AUTH_CONFIG;
  }

  const enabled =
    (import.meta.env.VITE_INTERNAL_AUTH as string | undefined) === "true";
  const convexAuthToken =
    normalizeEnvValue(
      import.meta.env.VITE_CONVEX_AUTH_TOKEN as string | undefined,
    ) ??
    normalizeEnvValue(
      import.meta.env.VITE_INTERNAL_CONVEX_AUTH_TOKEN as string | undefined,
    );

  const email = normalizeEnvValue(
    import.meta.env.VITE_INTERNAL_USER_EMAIL as string | undefined,
  );
  const name = normalizeEnvValue(
    import.meta.env.VITE_INTERNAL_USER_NAME as string | undefined,
  );

  if (!enabled && !convexAuthToken && !email && !name) {
    return null;
  }

  return {
    enabled: enabled || !!convexAuthToken || !!email || !!name,
    convexAuthToken,
    user:
      email || name
        ? {
            email,
            name,
          }
        : undefined,
  };
}

export function isInternalAuthEnabled(): boolean {
  return !!getInternalAuthConfig()?.enabled;
}
