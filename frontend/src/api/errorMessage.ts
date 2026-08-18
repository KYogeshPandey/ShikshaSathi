import { ApiError } from "./client";

export function apiErrorMessage(error: Error | null): string | null {
  if (!error) return null;
  if (error instanceof ApiError) return error.message;
  return "The request could not be completed.";
}
