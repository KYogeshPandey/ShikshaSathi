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

export interface RefreshResponse {
  token: AccessTokenInfo;
}
