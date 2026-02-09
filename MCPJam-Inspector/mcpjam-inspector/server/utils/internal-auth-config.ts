export type InternalAuthUiConfig = {
  enabled: true;
  convexAuthToken?: string;
  user?: {
    id?: string;
    email?: string;
    firstName?: string;
    lastName?: string;
    name?: string;
    profilePictureUrl?: string;
    imageUrl?: string;
    avatar?: string;
  };
};

const normalizeValue = (value?: string): string | undefined => {
  if (!value) return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
};

export const getInternalAuthUiConfig = (): InternalAuthUiConfig | null => {
  const enabledFlag = process.env.MCPJAM_INTERNAL_AUTH === "true";
  const convexAuthToken = normalizeValue(
    process.env.CONVEX_AUTH_TOKEN ||
      process.env.MCPJAM_INTERNAL_CONVEX_AUTH_TOKEN,
  );

  const email = normalizeValue(process.env.MCPJAM_INTERNAL_USER_EMAIL);
  const name = normalizeValue(process.env.MCPJAM_INTERNAL_USER_NAME);
  const firstName = normalizeValue(process.env.MCPJAM_INTERNAL_USER_FIRST_NAME);
  const lastName = normalizeValue(process.env.MCPJAM_INTERNAL_USER_LAST_NAME);

  const enabled =
    enabledFlag || !!convexAuthToken || !!email || !!name || !!firstName;

  if (!enabled) {
    return null;
  }

  const user =
    email || name || firstName || lastName
      ? {
          email,
          name,
          firstName,
          lastName,
        }
      : undefined;

  return {
    enabled: true,
    convexAuthToken: convexAuthToken ?? undefined,
    user,
  };
};
