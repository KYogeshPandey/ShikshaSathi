import type { AuthUser, UserRole } from "../types/auth";

export function makeUser(role: UserRole): AuthUser {
  return {
    id: `${role}-user-id`,
    email: `${role}@school.test`,
    full_name: `${role[0].toUpperCase()}${role.slice(1)} User`,
    role,
    is_active: true,
    created_at: "2026-08-16T10:00:00Z",
  };
}
