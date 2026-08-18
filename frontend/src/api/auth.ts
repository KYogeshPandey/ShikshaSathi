import { apiClient } from "./client";
import { authSession } from "../auth/session";
import type { AuthUser, LoginCredentials, LoginResponse } from "../types/auth";

export const authApi = {
  async restoreSession(): Promise<AuthUser | null> {
    try {
      await apiClient.refreshAccessToken();
      return await apiClient.get<AuthUser>("/auth/me");
    } catch {
      authSession.clearAccessToken();
      return null;
    }
  },

  async login(credentials: LoginCredentials): Promise<AuthUser> {
    const response = await apiClient.post<LoginResponse>("/auth/login", credentials, {
      auth: false,
      retryOnUnauthorized: false,
    });
    authSession.setAccessToken(response.token.access_token);
    return apiClient.get<AuthUser>("/auth/me");
  },

  async logout(): Promise<void> {
    try {
      await apiClient.post<{ detail: string }>("/auth/logout", undefined, {
        auth: false,
        retryOnUnauthorized: false,
      });
    } finally {
      authSession.clearAccessToken();
    }
  },
};
