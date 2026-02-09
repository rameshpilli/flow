import { useConvexAuth as useBaseConvexAuth } from "convex/react";
import { isInternalAuthEnabled } from "@/lib/auth";

export function useConvexAuth() {
  const auth = useBaseConvexAuth();
  if (!isInternalAuthEnabled()) {
    return auth;
  }
  return {
    ...auth,
    isAuthenticated: true,
    isLoading: false,
  };
}
