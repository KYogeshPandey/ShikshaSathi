import { afterEach, describe, expect, it, vi } from "vitest";
import { authSession } from "../auth/session";
import type { AuthUser } from "../types/auth";
import { authApi } from "./auth";
import { apiClient } from "./client";

const user: AuthUser = {
  id: "teacher-id",
  email: "teacher@registered-domain.dev",
  full_name: "Teacher User",
  role: "teacher",
  is_active: true,
  created_at: "2026-08-23T00:00:00Z",
};

afterEach(() => {
  authSession.clearAccessToken();
  vi.restoreAllMocks();
});

describe("OTP auth API flow", () => {
  it("does not create a client session when login returns an OTP challenge", async () => {
    const challenge = {
      otp_required: true as const,
      challenge_id: "challenge-id",
      expires_in: 300,
      resend_available_in: 30,
    };
    vi.spyOn(apiClient, "post").mockResolvedValue(challenge);
    const get = vi.spyOn(apiClient, "get");

    await expect(
      authApi.login({ email: user.email, password: "not-logged-or-stored" }),
    ).resolves.toEqual(challenge);
    expect(authSession.getAccessToken()).toBeNull();
    expect(get).not.toHaveBeenCalled();
  });

  it("stores the existing access token and resolves the current user after OTP verification", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      user,
      token: { access_token: "verified-access-token", token_type: "bearer", expires_in: 900 },
    });
    vi.spyOn(apiClient, "get").mockResolvedValue(user);

    await expect(authApi.verifyOtp("challenge-id", "123456")).resolves.toEqual(user);
    expect(post).toHaveBeenCalledWith(
      "/auth/otp/verify",
      { challenge_id: "challenge-id", otp: "123456" },
      { auth: false, retryOnUnauthorized: false },
    );
    expect(authSession.getAccessToken()).toBe("verified-access-token");
  });

  it("replaces a challenge through the resend endpoint", async () => {
    const replacement = {
      otp_required: true as const,
      challenge_id: "replacement-id",
      expires_in: 300,
      resend_available_in: 30,
    };
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(replacement);

    await expect(authApi.resendOtp("original-id")).resolves.toEqual(replacement);
    expect(post).toHaveBeenCalledWith(
      "/auth/otp/resend",
      { challenge_id: "original-id" },
      { auth: false, retryOnUnauthorized: false },
    );
  });
});

describe("password reset API flow", () => {
  it("requests and resends with generic same-origin auth-free calls", async () => {
    const publicResult = {
      detail: "If an active account exists for that email, a verification code has been sent.",
      expires_in: 300,
      resend_available_in: 30,
    };
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(publicResult);

    await expect(authApi.requestPasswordReset(user.email)).resolves.toEqual(publicResult);
    expect(post).toHaveBeenCalledWith(
      "/auth/password-reset/request",
      { email: user.email },
      { auth: false, retryOnUnauthorized: false },
    );

    await expect(authApi.resendPasswordResetOtp(user.email)).resolves.toEqual(publicResult);
    expect(post).toHaveBeenLastCalledWith(
      "/auth/password-reset/resend",
      { email: user.email },
      { auth: false, retryOnUnauthorized: false },
    );
  });

  it("never creates a client auth session while verifying or confirming reset", async () => {
    const grant = {
      reset_id: "reset-id",
      reset_token: "single-purpose-reset-token",
      expires_in: 120,
    };
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValueOnce(grant)
      .mockResolvedValueOnce({ detail: "Password updated." });
    const get = vi.spyOn(apiClient, "get");

    await expect(authApi.verifyPasswordResetOtp(user.email, "123456")).resolves.toEqual(grant);
    expect(post).toHaveBeenCalledWith(
      "/auth/password-reset/verify",
      { email: user.email, otp: "123456" },
      { auth: false, retryOnUnauthorized: false },
    );
    expect(authSession.getAccessToken()).toBeNull();

    await expect(
      authApi.confirmPasswordReset(
        grant.reset_id,
        grant.reset_token,
        "new-password-secure-456",
        "new-password-secure-456",
      ),
    ).resolves.toEqual({ detail: "Password updated." });
    expect(post).toHaveBeenLastCalledWith(
      "/auth/password-reset/confirm",
      {
        reset_id: "reset-id",
        reset_token: "single-purpose-reset-token",
        new_password: "new-password-secure-456",
        confirm_password: "new-password-secure-456",
      },
      { auth: false, retryOnUnauthorized: false },
    );
    expect(authSession.getAccessToken()).toBeNull();
    expect(get).not.toHaveBeenCalled();
  });
});
