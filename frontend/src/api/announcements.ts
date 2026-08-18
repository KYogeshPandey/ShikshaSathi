import { apiClient } from "./client";
import { withQuery } from "./params";
import type {
  Announcement,
  AnnouncementCreate,
  AnnouncementUpdate,
  Page,
} from "../types/domain";

export const announcementsApi = {
  list: (includeInactive = false, offset = 0) =>
    apiClient.get<Page<Announcement>>(
      withQuery("/announcements", {
        include_inactive: includeInactive,
        limit: 100,
        offset,
      }),
    ),
  create: (payload: AnnouncementCreate) =>
    apiClient.post<Announcement>("/announcements", payload),
  update: (id: string, payload: AnnouncementUpdate) =>
    apiClient.patch<Announcement>(`/announcements/${id}`, payload),
  deactivate: (id: string) => apiClient.delete<Announcement>(`/announcements/${id}`),
};
