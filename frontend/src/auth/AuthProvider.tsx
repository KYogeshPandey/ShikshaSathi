import { useCallback, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { authApi } from "../api/auth";
import {
  isOtpChallenge,
  type AuthUser,
  type LoginCredentials,
  type LoginResult,
  type OtpChallengeInfo,
  type PasswordResetConfirmResult,
  type PasswordResetGrant,
  type PasswordResetRequestInfo,
} from "../types/auth";
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
    async (credentials: LoginCredentials): Promise<LoginResult> => {
      const result = await authApi.login(credentials);
      if (!isOtpChallenge(result)) {
        queryClient.setQueryData<AuthUser | null>(authQueryKey, result);
      }
      return result;
    },
    [queryClient],
  );

  const verifyOtp = useCallback(
    async (challengeId: string, otp: string): Promise<AuthUser> => {
      const user = await authApi.verifyOtp(challengeId, otp);
      queryClient.setQueryData<AuthUser | null>(authQueryKey, user);
      return user;
    },
    [queryClient],
  );

  const loginDemoStudent = useCallback(async (): Promise<AuthUser> => {
    const demoUser = await authApi.loginDemoStudent();
    queryClient.setQueryData<AuthUser | null>(authQueryKey, demoUser);
    return demoUser;
  }, [queryClient]);

  const resendOtp = useCallback(
    (challengeId: string): Promise<OtpChallengeInfo> => authApi.resendOtp(challengeId),
    [],
  );

  const requestPasswordReset = useCallback(
    (email: string): Promise<PasswordResetRequestInfo> => authApi.requestPasswordReset(email),
    [],
  );

  const verifyPasswordResetOtp = useCallback(
    (email: string, otp: string): Promise<PasswordResetGrant> =>
      authApi.verifyPasswordResetOtp(email, otp),
    [],
  );

  const resendPasswordResetOtp = useCallback(
    (email: string): Promise<PasswordResetRequestInfo> =>
      authApi.resendPasswordResetOtp(email),
    [],
  );

  const confirmPasswordReset = useCallback(
    (
      resetId: string,
      resetToken: string,
      newPassword: string,
      confirmPassword: string,
    ): Promise<PasswordResetConfirmResult> =>
      authApi.confirmPasswordReset(resetId, resetToken, newPassword, confirmPassword),
    [],
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
    <AuthContext.Provider
      value={{
        status,
        user,
        login,
        loginDemoStudent,
        verifyOtp,
        resendOtp,
        requestPasswordReset,
        verifyPasswordResetOtp,
        resendPasswordResetOtp,
        confirmPasswordReset,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
