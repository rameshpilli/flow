import {
  type PropsWithChildren,
  createContext,
  useCallback,
  useContext,
  useMemo,
} from "react";
import {
  AuthKitProvider,
  useAuth as useWorkosAuth,
} from "@workos-inc/authkit-react";
import {
  getInternalAuthConfig,
  isInternalAuthEnabled,
  type InternalAuthUser,
} from "./internal-auth-config";

type AuthContextValue = {
  user: InternalAuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  signIn: () => void;
  signUp: () => void;
  signOut: () => void;
  getAccessToken: () => Promise<string | null>;
};

type WorkOsProviderConfig = {
  clientId: string;
  redirectUri: string;
  apiHostname?: string;
  https?: boolean;
  port?: number;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const noop = () => {};

function buildInternalUser(configUser?: InternalAuthUser | null): InternalAuthUser {
  const fallbackFirst = "Internal";
  const fallbackLast = "User";
  const firstName = configUser?.firstName ?? fallbackFirst;
  const lastName = configUser?.lastName ?? fallbackLast;
  const name =
    configUser?.name ?? `${firstName}${lastName ? ` ${lastName}` : ""}`;
  const email = configUser?.email ?? "internal@example.com";

  return {
    id: configUser?.id ?? "internal-user",
    email,
    firstName,
    lastName,
    name,
    profilePictureUrl: configUser?.profilePictureUrl,
    imageUrl: configUser?.imageUrl,
    avatar: configUser?.avatar,
  };
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

export function InternalAuthProvider({ children }: PropsWithChildren) {
  const config = getInternalAuthConfig();
  const user = useMemo(
    () => buildInternalUser(config?.user ?? null),
    [config?.user],
  );
  const getAccessToken = useCallback(async () => {
    return config?.convexAuthToken ?? null;
  }, [config?.convexAuthToken]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading: false,
      isAuthenticated: true,
      signIn: noop,
      signUp: noop,
      signOut: noop,
      getAccessToken,
    }),
    [user, getAccessToken],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function WorkOsAuthBridge({ children }: PropsWithChildren) {
  const workos = useWorkosAuth();

  const value = useMemo<AuthContextValue>(
    () => ({
      user: (workos.user as InternalAuthUser | null) ?? null,
      isLoading: workos.isLoading,
      isAuthenticated: workos.isAuthenticated,
      signIn: workos.signIn ?? noop,
      signUp: workos.signUp ?? noop,
      signOut: workos.signOut ?? noop,
      getAccessToken:
        workos.getAccessToken ?? (async () => Promise.resolve(null)),
    }),
    [
      workos.user,
      workos.isLoading,
      workos.isAuthenticated,
      workos.signIn,
      workos.signUp,
      workos.signOut,
      workos.getAccessToken,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function WorkOsAuthProvider({
  children,
  config,
}: PropsWithChildren<{ config: WorkOsProviderConfig }>) {
  return (
    <AuthKitProvider
      clientId={config.clientId}
      redirectUri={config.redirectUri}
      {...(config.apiHostname ? { apiHostname: config.apiHostname } : {})}
      {...(config.https !== undefined ? { https: config.https } : {})}
      {...(config.port ? { port: config.port } : {})}
    >
      <WorkOsAuthBridge>{children}</WorkOsAuthBridge>
    </AuthKitProvider>
  );
}

export { isInternalAuthEnabled };
