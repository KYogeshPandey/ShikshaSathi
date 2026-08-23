export const userRoles = ["admin", "teacher", "student"] as const;

export type UserRole = (typeof userRoles)[number];

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface AccessTokenInfo {
  access_token: string;
  token_type: "bearer" | string;
  expires_in: number;
}

export interface LoginResponse {
  user: AuthUser;
  token: AccessTokenInfo;
}

export interface OtpChallengeInfo {
  otp_required: true;
  challenge_id: string;
  expires_in: number;
  resend_available_in: number;
}

export type LoginResult = AuthUser | OtpChallengeInfo;

export function isOtpChallenge(result: LoginResult): result is OtpChallengeInfo {
  return "otp_required" in result && result.otp_required === true;
}

export interface RefreshResponse {
  token: AccessTokenInfo;
}
