import { apiClient } from "./client";
import { withQuery } from "./params";
import type { AnalyticsOverview, AnalyticsWindowDays } from "../types/domain";

export const analyticsApi = {
  getOverview: (days: AnalyticsWindowDays) =>
    apiClient.get<AnalyticsOverview>(withQuery("/analytics/overview", { days })),
};
