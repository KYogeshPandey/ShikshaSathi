import { apiClient } from "./client";
import { authSession } from "../auth/session";
import {
  type AuthUser,
  type LoginCredentials,
  type LoginResponse,
  type LoginResult,
  type OtpChallengeInfo,
  type PasswordResetConfirmResult,
  type PasswordResetGrant,
  type PasswordResetRequestInfo,
} from "../types/auth";

async function establishSession(response: LoginResponse): Promise<AuthUser> {
  authSession.setAccessToken(response.token.access_token);
  return apiClient.get<AuthUser>("/auth/me");
}

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
    return establishSession(response);
  },

  async loginDemoStudent(): Promise<AuthUser> {
    const response = await apiClient.post<LoginResponse>("/auth/demo-student", undefined, {
      auth: false,
      retryOnUnauthorized: false,
    });
    return establishSession(response);
  },

  async verifyOtp(challengeId: string, otp: string): Promise<AuthUser> {
    const response = await apiClient.post<LoginResponse>(
      "/auth/otp/verify",
      { challenge_id: challengeId, otp },
      { auth: false, retryOnUnauthorized: false },
    );
    return establishSession(response);
  },

  async resendOtp(challengeId: string): Promise<OtpChallengeInfo> {
    return apiClient.post<OtpChallengeInfo>(
      "/auth/otp/resend",
      { challenge_id: challengeId },
      { auth: false, retryOnUnauthorized: false },
    );
  },

  async requestPasswordReset(email: string): Promise<PasswordResetRequestInfo> {
    return apiClient.post<PasswordResetRequestInfo>(
      "/auth/password-reset/request",
      { email },
      { auth: false, retryOnUnauthorized: false },
    );
  },

  async verifyPasswordResetOtp(email: string, otp: string): Promise<PasswordResetGrant> {
    return apiClient.post<PasswordResetGrant>(
      "/auth/password-reset/verify",
      { email, otp },
      { auth: false, retryOnUnauthorized: false },
    );
  },

  async resendPasswordResetOtp(email: string): Promise<PasswordResetRequestInfo> {
    return apiClient.post<PasswordResetRequestInfo>(
      "/auth/password-reset/resend",
      { email },
      { auth: false, retryOnUnauthorized: false },
    );
  },

  async confirmPasswordReset(
    resetId: string,
    resetToken: string,
    newPassword: string,
    confirmPassword: string,
  ): Promise<PasswordResetConfirmResult> {
    return apiClient.post<PasswordResetConfirmResult>(
      "/auth/password-reset/confirm",
      {
        reset_id: resetId,
        reset_token: resetToken,
        new_password: newPassword,
        confirm_password: confirmPassword,
      },
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
