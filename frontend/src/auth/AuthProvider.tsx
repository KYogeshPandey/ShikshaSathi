import { useCallback, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { authApi } from "../api/auth";
import type { AuthUser, LoginCredentials } from "../types/auth";
import { AuthContext, authQueryKey, type AuthStatus } from "./authContext";
import { authSession } from "./session";

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const queryClient = useQueryClient();
  const authQuery = useQuery({
    queryKey: authQueryKey,
    queryFn: authApi.restoreSession,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });

  useEffect(
    () =>
      authSession.setUnauthorizedHandler(() => {
        queryClient.removeQueries({
          predicate: (query) => query.queryKey[0] !== "auth",
        });
        queryClient.setQueryData<AuthUser | null>(authQueryKey, null);
      }),
    [queryClient],
  );

  const login = useCallback(
    async (credentials: LoginCredentials): Promise<AuthUser> => {
      const user = await authApi.login(credentials);
      queryClient.setQueryData<AuthUser | null>(authQueryKey, user);
      return user;
    },
    [queryClient],
  );

  const logout = useCallback(async (): Promise<void> => {
    try {
      await authApi.logout();
    } finally {
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== "auth",
      });
      queryClient.setQueryData<AuthUser | null>(authQueryKey, null);
    }
  }, [queryClient]);

  const user = authQuery.data ?? null;
  const status: AuthStatus = authQuery.isPending
    ? "loading"
    : user
      ? "authenticated"
      : "unauthenticated";

  return (
    <AuthContext.Provider value={{ status, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
