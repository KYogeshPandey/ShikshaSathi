import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/client";

export function shouldRetryRequest(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && [401, 403, 422].includes(error.status)) {
    return false;
  }
  return failureCount < 1;
}

export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: shouldRetryRequest,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export const queryClient = createAppQueryClient();
