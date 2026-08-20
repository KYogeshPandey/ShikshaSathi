import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import type { AuthUser, LoginCredentials, UserRole } from "../types/auth";
import { AuthProvider } from "../auth/AuthProvider";
import { createAppQueryClient } from "../lib/queryClient";
import { makeUser } from "../test/testUsers";
import { App } from "./App";

const authApiMocks = vi.hoisted(() => ({
  restoreSession: vi.fn<() => Promise<AuthUser | null>>(),
  login: vi.fn<(credentials: LoginCredentials) => Promise<AuthUser>>(),
  logout: vi.fn<() => Promise<void>>(),
}));

vi.mock("../api/auth", () => ({ authApi: authApiMocks }));

const dashboardApiMocks = vi.hoisted(() => ({
  getMyTeacherProfile: vi.fn(),
  getMyStudentProfile: vi.fn(),
  getMyStats: vi.fn(),
  listClassrooms: vi.fn(),
  listSubjects: vi.fn(),
  listTimetable: vi.fn(),
}));

vi.mock("../api/profiles", () => ({ profilesApi: {
  getMyTeacherProfile: dashboardApiMocks.getMyTeacherProfile,
  getMyStudentProfile: dashboardApiMocks.getMyStudentProfile,
} }));
vi.mock("../api/attendance", () => ({ attendanceApi: { getMyStats: dashboardApiMocks.getMyStats } }));
vi.mock("../api/academics", () => ({ academicsApi: {
  listClassrooms: dashboardApiMocks.listClassrooms,
  listSubjects: dashboardApiMocks.listSubjects,
  listTimetable: dashboardApiMocks.listTimetable,
} }));

function renderApplication(path: string) {
  const client = createAppQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  authApiMocks.restoreSession.mockReset();
  authApiMocks.login.mockReset();
  authApiMocks.logout.mockReset();
  authApiMocks.restoreSession.mockResolvedValue(null);
  authApiMocks.logout.mockResolvedValue();
  const resource = { is_active: true, created_at: "2026-08-16T00:00:00Z", updated_at: "2026-08-16T00:00:00Z" };
  dashboardApiMocks.getMyTeacherProfile.mockResolvedValue({ ...resource, id: "teacher-profile", user_id: "teacher-user", employee_code: "T-7", phone_number: null });
  dashboardApiMocks.getMyStudentProfile.mockResolvedValue({ ...resource, id: "student-profile", user_id: "student-user", classroom_id: null, roll_number: "7" });
  dashboardApiMocks.getMyStats.mockResolvedValue({ student_profile_id: "student-profile", total_count: 10, present_count: 8, absent_count: 2, attendance_percentage: 80 });
  dashboardApiMocks.listClassrooms.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
  dashboardApiMocks.listSubjects.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
  dashboardApiMocks.listTimetable.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
});

describe("application and authentication", () => {
  it("renders the public landing page at the application root", async () => {
    renderApplication("/");
    expect(
      await screen.findByRole("heading", {
        name: /one workspace for smarter school operations/i,
      }),
    ).toBeVisible();
  });

  it("closes the landing navigation with Escape and returns focus to its trigger", async () => {
    renderApplication("/");
    await screen.findByRole("heading", { name: /one workspace for smarter school operations/i });
    const menuButton = document.querySelector<HTMLButtonElement>(".ss-menu-button");
    expect(menuButton).not.toBeNull();

    fireEvent.click(menuButton!);
    expect(menuButton).toHaveAttribute("aria-label", "Close menu");
    fireEvent.keyDown(window, { key: "Escape" });

    expect(menuButton).toHaveAttribute("aria-label", "Open menu");
    expect(menuButton).toHaveFocus();
  });

  it("shows the auth bootstrap loading state", () => {
    authApiMocks.restoreSession.mockReturnValue(new Promise(() => undefined));
    renderApplication("/student");
    expect(screen.getByText(/restoring your session/i)).toBeVisible();
  });

  it("validates the login form before calling the API", async () => {
    const user = userEvent.setup();
    renderApplication("/login");

    await user.click(await screen.findByRole("button", { name: /^sign in$/i }));

    expect(await screen.findByText(/email is required/i)).toBeVisible();
    expect(screen.getByText(/password is required/i)).toBeVisible();
    expect(authApiMocks.login).not.toHaveBeenCalled();
  });

  it("redirects to the authenticated user's role after a successful login", async () => {
    const teacher = makeUser("teacher");
    authApiMocks.login.mockResolvedValue(teacher);
    const user = userEvent.setup();
    renderApplication("/login");

    await user.type(await screen.findByLabelText(/email/i), "teacher@school.test");
    await user.type(screen.getByLabelText(/password/i), "correct horse battery staple");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(await screen.findByRole("heading", { name: /teacher workspace/i })).toBeVisible();
    expect(authApiMocks.login).toHaveBeenCalledWith({
      email: "teacher@school.test",
      password: "correct horse battery staple",
    });
  });

  it("shows a specific message for invalid credentials", async () => {
    authApiMocks.login.mockRejectedValue(new ApiError(401, "INVALID_CREDENTIALS", "Invalid credentials."));
    const user = userEvent.setup();
    renderApplication("/login");

    await user.type(await screen.findByLabelText(/email/i), "teacher@school.test");
    await user.type(screen.getByLabelText(/password/i), "incorrect password");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
  });

  it("distinguishes a temporarily unavailable service from an authentication failure", async () => {
    authApiMocks.login.mockRejectedValue(new ApiError(503, "SERVICE_UNAVAILABLE", "Internal detail."));
    const user = userEvent.setup();
    renderApplication("/login");

    await user.type(await screen.findByLabelText(/email/i), "teacher@school.test");
    await user.type(screen.getByLabelText(/password/i), "any password");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The server is temporarily unavailable. Please try again shortly.",
    );
    expect(screen.queryByText("Internal detail.")).not.toBeInTheDocument();
  });

  it("redirects an unauthenticated protected route to login", async () => {
    renderApplication("/student/attendance");
    expect(await screen.findByRole("heading", { name: /sign in to continue/i })).toBeVisible();
  });

  it("clears auth state and returns to login on logout", async () => {
    authApiMocks.restoreSession.mockResolvedValue(makeUser("admin"));
    const user = userEvent.setup();
    renderApplication("/admin");

    await user.click(await screen.findByRole("button", { name: /sign out/i }));

    expect(await screen.findByRole("heading", { name: /sign in to continue/i })).toBeVisible();
    expect(authApiMocks.logout).toHaveBeenCalledOnce();
  });
});

describe("role routing", () => {
  const allowedCases: ReadonlyArray<[UserRole, string, RegExp]> = [
    ["admin", "/admin", /administration workspace/i],
    ["teacher", "/teacher", /teacher workspace/i],
    ["student", "/student", /student portal/i],
  ];

  it.each(allowedCases)(
    "allows an authenticated %s to render its role shell",
    async (role, path, heading) => {
      authApiMocks.restoreSession.mockResolvedValue(makeUser(role));
      renderApplication(path);
      expect(await screen.findByRole("heading", { name: heading })).toBeVisible();
      expect(screen.getByText(`${role}@school.test`)).toBeVisible();
    },
  );

  const deniedCases: ReadonlyArray<[UserRole, string]> = [
    ["admin", "/teacher"],
    ["teacher", "/student"],
    ["student", "/admin"],
  ];

  it.each(deniedCases)(
    "blocks a %s from a different role route",
    async (role, requestedPath) => {
      authApiMocks.restoreSession.mockResolvedValue(makeUser(role));
      renderApplication(requestedPath);
      expect(await screen.findByRole("heading", { name: /assigned to another role/i })).toBeVisible();
    },
  );

  it("renders an authenticated student's nested wildcard route without throwing", async () => {
    authApiMocks.restoreSession.mockResolvedValue(makeUser("student"));
    renderApplication("/student/a-future-page");

    expect(await screen.findByText(/student@school.test/i)).toBeVisible();
    expect(screen.getByRole("heading", { name: /page not available/i })).toBeVisible();
    expect(screen.getByRole("navigation", { name: /student navigation/i })).toBeVisible();
  });

  it("does not expose a student route to a teacher", async () => {
    authApiMocks.restoreSession.mockResolvedValue(makeUser("teacher"));
    renderApplication("/student/attendance");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /assigned to another role/i })).toBeVisible();
    });
  });

  it.each([
    ["admin", "/admin/reports"],
    ["teacher", "/teacher/reports"],
  ] as const)("exposes reports inside the %s role shell", async (role, path) => {
    authApiMocks.restoreSession.mockResolvedValue(makeUser(role));
    renderApplication(path);
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Reports" })).toBeVisible();
  });

  it("does not expose reports in the student portal", async () => {
    authApiMocks.restoreSession.mockResolvedValue(makeUser("student"));
    renderApplication("/student/reports");
    expect(await screen.findByRole("heading", { name: /page not available/i })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Reports" })).not.toBeInTheDocument();
  });
});
