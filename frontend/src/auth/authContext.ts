import { createContext, useContext } from "react";
import type { AuthUser, LoginCredentials, LoginResult, OtpChallengeInfo } from "../types/auth";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  login(credentials: LoginCredentials): Promise<LoginResult>;
  verifyOtp(challengeId: string, otp: string): Promise<AuthUser>;
  resendOtp(challengeId: string): Promise<OtpChallengeInfo>;
  logout(): Promise<void>;
}

export const authQueryKey = ["auth", "current-user"] as const;

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return context;
}
