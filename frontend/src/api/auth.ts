import { apiClient } from "./client";
import { authSession } from "../auth/session";
import {
  type AuthUser,
  type LoginCredentials,
  type LoginResponse,
  type LoginResult,
  type OtpChallengeInfo,
} from "../types/auth";

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

  async login(credentials: LoginCredentials): Promise<LoginResult> {
    const response = await apiClient.post<LoginResponse | OtpChallengeInfo>("/auth/login", credentials, {
      auth: false,
      retryOnUnauthorized: false,
    });
    if ("otp_required" in response) return response;
    authSession.setAccessToken(response.token.access_token);
    return apiClient.get<AuthUser>("/auth/me");
  },

  async verifyOtp(challengeId: string, otp: string): Promise<AuthUser> {
    const response = await apiClient.post<LoginResponse>(
      "/auth/otp/verify",
      { challenge_id: challengeId, otp },
      { auth: false, retryOnUnauthorized: false },
    );
    authSession.setAccessToken(response.token.access_token);
    return apiClient.get<AuthUser>("/auth/me");
  },

  async resendOtp(challengeId: string): Promise<OtpChallengeInfo> {
    return apiClient.post<OtpChallengeInfo>(
      "/auth/otp/resend",
      { challenge_id: challengeId },
      { auth: false, retryOnUnauthorized: false },
    );
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
