import { apiClient } from "./client";
import { withQuery } from "./params";
import type { Page, UserDirectoryEntry } from "../types/domain";

export const usersApi = {
  list(
    role: "teacher" | "student",
    options: { includeInactive?: boolean; limit?: number; offset?: number } = {},
  ): Promise<Page<UserDirectoryEntry>> {
    return apiClient.get<Page<UserDirectoryEntry>>(
      withQuery("/users", {
        role,
        include_inactive: options.includeInactive,
        limit: options.limit ?? 100,
        offset: options.offset ?? 0,
      }),
    );
  },
};
