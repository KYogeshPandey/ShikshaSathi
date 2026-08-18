import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryAuthSession } from "../auth/session";
import { ApiClient } from "./client";

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorEnvelope(code: string, message: string) {
  return {
    error: { code, message, details: {} },
    request_id: "request-id",
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("centralized 401 handling", () => {
  it("refreshes once and retries the protected request with the new access token", async () => {
    const session = new MemoryAuthSession();
    session.setAccessToken("expired-access-token");
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(errorEnvelope("AUTHENTICATION_ERROR", "Expired."), 401))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            token: {
              access_token: "new-access-token",
              token_type: "bearer",
              expires_in: 900,
            },
          },
          200,
        ),
      )
      .mockResolvedValueOnce(jsonResponse({ result: "ok" }, 200));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("https://api.school.test/api/v1", session);

    await expect(client.get<{ result: string }>("/protected")).resolves.toEqual({ result: "ok" });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1]?.[0]).toBe("https://api.school.test/api/v1/auth/refresh");
    expect(fetchMock.mock.calls[1]?.[1]?.credentials).toBe("include");
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Authorization")).toBe(
      "Bearer expired-access-token",
    );
    expect(new Headers(fetchMock.mock.calls[2]?.[1]?.headers).get("Authorization")).toBe(
      "Bearer new-access-token",
    );
  });

  it("deduplicates concurrent refresh attempts", async () => {
    const session = new MemoryAuthSession();
    session.setAccessToken("expired-access-token");
    let releaseRefresh: ((response: Response) => void) | undefined;
    const refreshResponse = new Promise<Response>((resolve) => {
      releaseRefresh = resolve;
    });
    const fetchMock = vi.fn<typeof fetch>((url) => {
      if (String(url).endsWith("/auth/refresh")) return refreshResponse;
      return Promise.resolve(jsonResponse(errorEnvelope("AUTHENTICATION_ERROR", "Expired."), 401));
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("https://api.school.test/api/v1", session);

    const first = client.refreshAccessToken();
    const second = client.refreshAccessToken();
    releaseRefresh?.(
      jsonResponse(
        { token: { access_token: "fresh", token_type: "bearer", expires_in: 900 } },
        200,
      ),
    );

    await expect(Promise.all([first, second])).resolves.toEqual(["fresh", "fresh"]);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("clears frontend auth and notifies the provider when refresh fails", async () => {
    const session = new MemoryAuthSession();
    session.setAccessToken("expired-access-token");
    const onUnauthorized = vi.fn();
    session.setUnauthorizedHandler(onUnauthorized);
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(errorEnvelope("AUTHENTICATION_ERROR", "Expired."), 401))
      .mockResolvedValueOnce(
        jsonResponse(errorEnvelope("INVALID_REFRESH_TOKEN", "Refresh expired."), 401),
      );
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("https://api.school.test/api/v1", session);

    await expect(client.get("/protected")).rejects.toMatchObject({
      status: 401,
      code: "INVALID_REFRESH_TOKEN",
    });
    expect(session.getAccessToken()).toBeNull();
    expect(onUnauthorized).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not treat a 403 as an authentication refresh case", async () => {
    const session = new MemoryAuthSession();
    session.setAccessToken("valid-access-token");
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(errorEnvelope("FORBIDDEN", "Denied."), 403));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("https://api.school.test/api/v1", session);

    await expect(client.get("/protected")).rejects.toMatchObject({ status: 403 });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(session.getAccessToken()).toBe("valid-access-token");
  });
});

describe("authenticated binary downloads", () => {
  it("returns the response blob and safe server filename", async () => {
    const session = new MemoryAuthSession();
    session.setAccessToken("valid-access-token");
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(
      new Response("attendance_date\n", {
        status: 200,
        headers: {
          "Content-Disposition": 'attachment; filename="attendance-report.csv"',
          "Content-Type": "text/csv; charset=utf-8",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("https://api.school.test/api/v1", session);

    const result = await client.download("/reports/attendance/export.csv");

    expect(result.filename).toBe("attendance-report.csv");
    expect(result.contentType).toBe("text/csv; charset=utf-8");
    expect(result.blob.size).toBeGreaterThan(0);
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Authorization")).toBe(
      "Bearer valid-access-token",
    );
  });

  it("refreshes a binary request once after 401 and does not refresh after 403", async () => {
    const session = new MemoryAuthSession();
    session.setAccessToken("expired-access-token");
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(errorEnvelope("AUTHENTICATION_ERROR", "Expired."), 401))
      .mockResolvedValueOnce(
        jsonResponse(
          { token: { access_token: "fresh-access-token", token_type: "bearer", expires_in: 900 } },
          200,
        ),
      )
      .mockResolvedValueOnce(new Response("%PDF", { status: 200, headers: { "Content-Type": "application/pdf" } }))
      .mockResolvedValueOnce(jsonResponse(errorEnvelope("FORBIDDEN", "Denied."), 403));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("https://api.school.test/api/v1", session);

    await expect(client.download("/reports/attendance/export.pdf")).resolves.toMatchObject({
      contentType: "application/pdf",
    });
    await expect(client.download("/reports/attendance/export.pdf")).rejects.toMatchObject({
      status: 403,
    });

    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(new Headers(fetchMock.mock.calls[2]?.[1]?.headers).get("Authorization")).toBe(
      "Bearer fresh-access-token",
    );
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/auth/refresh"))).toHaveLength(1);
  });
});
