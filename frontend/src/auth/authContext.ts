import { createContext, useContext } from "react";
import type { AuthUser, LoginCredentials } from "../types/auth";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  login(credentials: LoginCredentials): Promise<AuthUser>;
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
