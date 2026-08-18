import { authSession, type AuthSessionStore } from "../auth/session";
import type { ApiErrorEnvelope } from "./types";
import type { RefreshResponse } from "../types/auth";

const DEFAULT_API_URL = "/api/v1";

function normalizeBaseUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

export const apiBaseUrl = normalizeBaseUrl(
  import.meta.env.VITE_API_URL?.trim() || DEFAULT_API_URL,
);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (!isRecord(value) || !isRecord(value.error)) {
    return false;
  }
  return (
    typeof value.error.code === "string" &&
    typeof value.error.message === "string" &&
    isRecord(value.error.details) &&
    typeof value.request_id === "string"
  );
}

function isRefreshResponse(value: unknown): value is RefreshResponse {
  if (!isRecord(value) || !isRecord(value.token)) {
    return false;
  }
  return (
    typeof value.token.access_token === "string" &&
    typeof value.token.token_type === "string" &&
    typeof value.token.expires_in === "number"
  );
}

function defaultErrorMessage(status: number): string {
  if (status === 401) return "Your session is no longer valid.";
  if (status === 403) return "You do not have permission to perform this action.";
  if (status >= 500) return "The service is temporarily unavailable.";
  return "The request could not be completed.";
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details: Record<string, unknown> = {},
    public readonly requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  auth?: boolean;
  retryOnUnauthorized?: boolean;
}

export interface ApiDownload {
  blob: Blob;
  contentType: string | null;
  filename: string | null;
}

function downloadFilename(disposition: string | null): string | null {
  if (!disposition) return null;
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  const candidate = encoded ? decodeURIComponent(encoded) : plain;
  if (!candidate) return null;
  return candidate.split(/[\\/]/).at(-1) ?? null;
}

export class ApiClient {
  private refreshPromise: Promise<string> | null = null;

  constructor(
    private readonly baseUrl: string = apiBaseUrl,
    private readonly session: AuthSessionStore = authSession,
  ) {}

  get<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  post<T>(path: string, body?: unknown, options: ApiRequestOptions = {}): Promise<T> {
    return this.request<T>(path, { ...options, body, method: "POST" });
  }

  put<T>(path: string, body?: unknown, options: ApiRequestOptions = {}): Promise<T> {
    return this.request<T>(path, { ...options, body, method: "PUT" });
  }

  patch<T>(path: string, body?: unknown, options: ApiRequestOptions = {}): Promise<T> {
    return this.request<T>(path, { ...options, body, method: "PATCH" });
  }

  delete<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "DELETE" });
  }

  async download(path: string, options: ApiRequestOptions = {}): Promise<ApiDownload> {
    const response = await this.send(path, {
      ...options,
      headers: { Accept: "*/*", ...options.headers },
      method: "GET",
    });
    return {
      blob: await response.blob(),
      contentType: response.headers.get("Content-Type"),
      filename: downloadFilename(response.headers.get("Content-Disposition")),
    };
  }

  async refreshAccessToken(): Promise<string> {
    if (!this.refreshPromise) {
      this.refreshPromise = this.performRefresh().finally(() => {
        this.refreshPromise = null;
      });
    }
    return this.refreshPromise;
  }

  private async performRefresh(): Promise<string> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
    } catch {
      throw new ApiError(0, "NETWORK_ERROR", "Unable to reach the service.");
    }

    const payload = await readJson(response);
    if (!response.ok) {
      throw this.toApiError(response.status, payload);
    }
    if (!isRefreshResponse(payload)) {
      throw new ApiError(0, "INVALID_API_RESPONSE", "The service returned an invalid response.");
    }

    this.session.setAccessToken(payload.token.access_token);
    return payload.token.access_token;
  }

  private async request<T>(path: string, options: ApiRequestOptions): Promise<T> {
    const response = await this.send(path, options);
    return (await readJson(response)) as T;
  }

  private async send(path: string, options: ApiRequestOptions): Promise<Response> {
    const {
      auth = true,
      retryOnUnauthorized = true,
      body,
      headers: suppliedHeaders,
      ...requestInit
    } = options;
    const headers = new Headers(suppliedHeaders);
    if (!headers.has("Accept")) headers.set("Accept", "application/json");

    const token = auth ? this.session.getAccessToken() : null;
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    let encodedBody: BodyInit | undefined;
    if (body instanceof FormData) {
      encodedBody = body;
    } else if (body !== undefined) {
      headers.set("Content-Type", "application/json");
      encodedBody = JSON.stringify(body);
    }

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        ...requestInit,
        body: encodedBody,
        credentials: "include",
        headers,
      });
    } catch {
      throw new ApiError(0, "NETWORK_ERROR", "Unable to reach the service.");
    }

    if (response.status === 401 && auth && retryOnUnauthorized) {
      try {
        await this.refreshAccessToken();
      } catch (error: unknown) {
        this.session.invalidate();
        throw error;
      }
      return this.send(path, {
        ...options,
        retryOnUnauthorized: false,
      });
    }

    if (!response.ok) {
      const payload = await readJson(response);
      throw this.toApiError(response.status, payload);
    }
    return response;
  }

  private toApiError(status: number, payload: unknown): ApiError {
    if (isErrorEnvelope(payload)) {
      return new ApiError(
        status,
        payload.error.code,
        payload.error.message,
        payload.error.details,
        payload.request_id,
      );
    }
    return new ApiError(status, `HTTP_${status}`, defaultErrorMessage(status));
  }
}

export const apiClient = new ApiClient();
