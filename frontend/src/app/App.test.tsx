import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import type {
  AuthUser,
  LoginCredentials,
  LoginResult,
  OtpChallengeInfo,
  PasswordResetConfirmResult,
  PasswordResetGrant,
  PasswordResetRequestInfo,
  UserRole,
} from "../types/auth";
import { AuthProvider } from "../auth/AuthProvider";
import { createAppQueryClient } from "../lib/queryClient";
import { makeUser } from "../test/testUsers";
import { App } from "./App";

const authApiMocks = vi.hoisted(() => ({
  restoreSession: vi.fn<() => Promise<AuthUser | null>>(),
  login: vi.fn<(credentials: LoginCredentials) => Promise<LoginResult>>(),
  verifyOtp: vi.fn<(challengeId: string, otp: string) => Promise<AuthUser>>(),
  resendOtp: vi.fn<(challengeId: string) => Promise<OtpChallengeInfo>>(),
  requestPasswordReset: vi.fn<(email: string) => Promise<PasswordResetRequestInfo>>(),
  verifyPasswordResetOtp: vi.fn<(email: string, otp: string) => Promise<PasswordResetGrant>>(),
  resendPasswordResetOtp: vi.fn<(email: string) => Promise<PasswordResetRequestInfo>>(),
  confirmPasswordReset: vi.fn<
    (
      resetId: string,
      resetToken: string,
      newPassword: string,
      confirmPassword: string,
    ) => Promise<PasswordResetConfirmResult>
  >(),
  logout: vi.fn<() => Promise<void>>(),
}));

vi.mock("../api/auth", () => ({ authApi: authApiMocks }));

const dashboardApiMocks = vi.hoisted(() => ({
  getOverview: vi.fn(),
  getMyTeacherProfile: vi.fn(),
  getMyStudentProfile: vi.fn(),
  getMyStats: vi.fn(),
  listClassrooms: vi.fn(),
  listSubjects: vi.fn(),
  listTimetable: vi.fn(),
}));

vi.mock("../api/analytics", () => ({ analyticsApi: { getOverview: dashboardApiMocks.getOverview } }));
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

function analyticsOverview(days: 7 | 30 = 7) {
  const dateTo = new Date(Date.UTC(2026, 7, 20));
  const dateFrom = new Date(dateTo);
  dateFrom.setUTCDate(dateFrom.getUTCDate() - days + 1);
  const previousTo = new Date(dateFrom);
  previousTo.setUTCDate(previousTo.getUTCDate() - 1);
  const previousFrom = new Date(previousTo);
  previousFrom.setUTCDate(previousFrom.getUTCDate() - days + 1);
  const isoDate = (value: Date) => value.toISOString().slice(0, 10);
  return {
    role: "admin" as const,
    period: { days, date_from: isoDate(dateFrom), date_to: isoDate(dateTo) },
    attendance: { total_count: 8, present_count: 6, absent_count: 2, attendance_percentage: 75 },
    comparison: {
      period: { days, date_from: isoDate(previousFrom), date_to: isoDate(previousTo) },
      attendance: { total_count: 10, present_count: 7, absent_count: 3, attendance_percentage: 70 },
      percentage_point_change: 5,
    },
    trend: Array.from({ length: days }, (_, index) => {
      const attendanceDate = new Date(dateFrom);
      attendanceDate.setUTCDate(attendanceDate.getUTCDate() + index);
      return {
        attendance_date: isoDate(attendanceDate),
        total_count: 1,
        present_count: index % 4 === 0 ? 0 : 1,
        absent_count: index % 4 === 0 ? 1 : 0,
        attendance_percentage: index % 4 === 0 ? 0 : 100,
      };
    }),
    attendance_definition: "present_marked_records_divided_by_all_marked_records" as const,
    missing_records_policy: "excluded_unmarked" as const,
    admin_population: { active_students: 120, active_teachers: 12, active_classrooms: 8, active_subjects: 10 },
    teacher_scope: { assigned_classrooms: 2, assigned_subjects: 3, timetable_slots: 6 },
    student_context: { roll_number: "7" },
    attention_classrooms: [{
      classroom_name: "Grade 8 A",
      classroom_code: "grade-8-a",
      total_count: 20,
      present_count: 14,
      absent_count: 6,
      attendance_percentage: 70,
    }],
  };
}

beforeEach(() => {
  authApiMocks.restoreSession.mockReset();
  authApiMocks.login.mockReset();
  authApiMocks.verifyOtp.mockReset();
  authApiMocks.resendOtp.mockReset();
  authApiMocks.requestPasswordReset.mockReset();
  authApiMocks.verifyPasswordResetOtp.mockReset();
  authApiMocks.resendPasswordResetOtp.mockReset();
  authApiMocks.confirmPasswordReset.mockReset();
  authApiMocks.logout.mockReset();
  authApiMocks.restoreSession.mockResolvedValue(null);
  authApiMocks.logout.mockResolvedValue();
  dashboardApiMocks.getOverview.mockReset();
  dashboardApiMocks.getOverview.mockImplementation(async (days: 7 | 30) => analyticsOverview(days));
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

  it("transitions through invalid OTP, resend, and successful verification", async () => {
    const teacher = makeUser("teacher");
    authApiMocks.login.mockResolvedValue({
      otp_required: true,
      challenge_id: "challenge-one",
      expires_in: 300,
      resend_available_in: 0,
    });
    authApiMocks.verifyOtp
      .mockRejectedValueOnce(new ApiError(401, "INVALID_OTP", "Invalid OTP."))
      .mockResolvedValueOnce(teacher);
    authApiMocks.resendOtp.mockResolvedValue({
      otp_required: true,
      challenge_id: "challenge-two",
      expires_in: 300,
      resend_available_in: 0,
    });
    const user = userEvent.setup();
    renderApplication("/login");

    await user.type(await screen.findByLabelText(/^email$/i), "teacher@any-domain.dev");
    await user.type(screen.getByLabelText(/password/i), "correct horse battery staple");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(await screen.findByRole("heading", { name: /enter your sign-in code/i })).toBeVisible();
    await user.type(screen.getByLabelText(/verification code/i), "123456");
    await user.click(screen.getByRole("button", { name: /verify and sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect or has already been used/i);

    await user.click(screen.getByRole("button", { name: /resend code/i }));
    expect(await screen.findByRole("status")).toHaveTextContent(/new verification code/i);
    expect(authApiMocks.resendOtp).toHaveBeenCalledWith("challenge-one");

    await user.type(screen.getByLabelText(/verification code/i), "654321");
    await user.click(screen.getByRole("button", { name: /verify and sign in/i }));
    expect(await screen.findByRole("heading", { name: /teacher workspace/i })).toBeVisible();
    expect(authApiMocks.verifyOtp).toHaveBeenLastCalledWith("challenge-two", "654321");
  });

  it("allows changing account from the OTP step", async () => {
    authApiMocks.login.mockResolvedValue({
      otp_required: true,
      challenge_id: "challenge-change-account",
      expires_in: 300,
      resend_available_in: 30,
    });
    const user = userEvent.setup();
    renderApplication("/login");
    await user.type(await screen.findByLabelText(/^email$/i), "teacher@domain.example");
    await user.type(screen.getByLabelText(/password/i), "correct horse battery staple");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    await user.click(await screen.findByRole("button", { name: /change account/i }));
    expect(screen.getByRole("heading", { name: /sign in to continue/i })).toBeVisible();
    expect(screen.getByLabelText(/^email$/i)).toHaveValue("");
  });

  it("shows an expired OTP error without authenticating", async () => {
    authApiMocks.login.mockResolvedValue({
      otp_required: true,
      challenge_id: "challenge-expired",
      expires_in: 1,
      resend_available_in: 0,
    });
    authApiMocks.verifyOtp.mockRejectedValue(
      new ApiError(410, "OTP_EXPIRED", "Expired."),
    );
    const user = userEvent.setup();
    renderApplication("/login");
    await user.type(await screen.findByLabelText(/^email$/i), "teacher@domain.dev");
    await user.type(screen.getByLabelText(/password/i), "correct horse battery staple");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));
    await user.click(await screen.findByLabelText(/verification code/i));
    await user.paste("123456");
    await user.click(screen.getByRole("button", { name: /verify and sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/code has expired/i);
    expect(authApiMocks.verifyOtp).toHaveBeenCalledWith("challenge-expired", "123456");
  });

  it("enforces the visible resend countdown before enabling the real button", async () => {
    authApiMocks.login.mockResolvedValue({
      otp_required: true,
      challenge_id: "challenge-countdown",
      expires_in: 300,
      resend_available_in: 1,
    });
    const user = userEvent.setup();
    renderApplication("/login");
    await user.type(await screen.findByLabelText(/^email$/i), "teacher@domain.dev");
    await user.type(screen.getByLabelText(/password/i), "correct horse battery staple");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(await screen.findByRole("button", { name: "Resend in 1s" })).toBeDisabled();
    expect(
      await screen.findByRole("button", { name: "Resend code" }, { timeout: 2_500 }),
    ).toBeEnabled();
  });

  it("requests password reset with generic copy and an accessible OTP step", async () => {
    authApiMocks.requestPasswordReset.mockResolvedValue({
      detail: "If an active account exists for that email, a verification code has been sent.",
      expires_in: 300,
      resend_available_in: 30,
    });
    const user = userEvent.setup();
    renderApplication("/login");

    await user.click(await screen.findByRole("button", { name: /forgot password/i }));
    expect(screen.getByRole("heading", { name: /reset your password/i })).toBeVisible();
    expect(screen.getByText(/enter your registered email address/i)).toBeVisible();
    await user.type(screen.getByLabelText(/^email$/i), "person@ordinary-domain.dev");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    expect(
      await screen.findByRole("heading", { name: /enter your verification code/i }),
    ).toBeVisible();
    expect(screen.getByText(/if an active account exists/i)).toBeVisible();
    expect(screen.getByLabelText(/verification code/i)).toHaveAttribute(
      "autocomplete",
      "one-time-code",
    );
    expect(authApiMocks.requestPasswordReset).toHaveBeenCalledWith(
      "person@ordinary-domain.dev",
    );
  });

  it("handles invalid reset OTP, resend, password mismatch, success, and return to sign in", async () => {
    const requestInfo = {
      detail: "If an active account exists for that email, a verification code has been sent.",
      expires_in: 300,
      resend_available_in: 0,
    };
    authApiMocks.requestPasswordReset.mockResolvedValue(requestInfo);
    authApiMocks.resendPasswordResetOtp.mockResolvedValue(requestInfo);
    authApiMocks.verifyPasswordResetOtp
      .mockRejectedValueOnce(new ApiError(401, "INVALID_OTP", "Internal detail."))
      .mockResolvedValueOnce({
        reset_id: "reset-id",
        reset_token: "reset-token-not-an-access-token",
        expires_in: 120,
      });
    authApiMocks.confirmPasswordReset.mockResolvedValue({
      detail: "Password updated. Sign in with your new password.",
    });
    const user = userEvent.setup();
    renderApplication("/login");

    await user.click(await screen.findByRole("button", { name: /forgot password/i }));
    await user.type(screen.getByLabelText(/^email$/i), "person@ordinary-domain.dev");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));
    await user.type(await screen.findByLabelText(/verification code/i), "123456");
    await user.click(screen.getByRole("button", { name: /^verify code$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect or has already been used/i);

    await user.click(screen.getByRole("button", { name: /resend code/i }));
    expect(await screen.findByRole("status")).toHaveTextContent(/if the account is active/i);
    expect(authApiMocks.resendPasswordResetOtp).toHaveBeenCalledWith(
      "person@ordinary-domain.dev",
    );

    await user.type(screen.getByLabelText(/verification code/i), "654321");
    await user.click(screen.getByRole("button", { name: /^verify code$/i }));
    expect(await screen.findByRole("heading", { name: /choose a new password/i })).toBeVisible();

    await user.type(screen.getByLabelText(/^new password$/i), "new-password-secure-456");
    await user.type(screen.getByLabelText(/confirm new password/i), "different-password-789");
    await user.click(screen.getByRole("button", { name: /update password/i }));
    expect(await screen.findByText(/passwords do not match/i)).toBeVisible();
    expect(authApiMocks.confirmPasswordReset).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText(/confirm new password/i));
    await user.type(screen.getByLabelText(/confirm new password/i), "new-password-secure-456");
    await user.click(screen.getByRole("button", { name: /update password/i }));
    expect(await screen.findByRole("heading", { name: /password has been reset/i })).toBeVisible();
    expect(authApiMocks.confirmPasswordReset).toHaveBeenCalledWith(
      "reset-id",
      "reset-token-not-an-access-token",
      "new-password-secure-456",
      "new-password-secure-456",
    );

    await user.click(screen.getByRole("button", { name: /return to sign in/i }));
    expect(screen.getByRole("heading", { name: /sign in to continue/i })).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(/password updated/i);
  });

  it("shows password-reset loading and sanitized unavailable feedback", async () => {
    let rejectRequest: ((reason: unknown) => void) | undefined;
    authApiMocks.requestPasswordReset.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectRequest = reject;
      }),
    );
    const user = userEvent.setup();
    renderApplication("/login");

    await user.click(await screen.findByRole("button", { name: /forgot password/i }));
    await user.type(screen.getByLabelText(/^email$/i), "person@ordinary-domain.dev");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));
    expect(screen.getByRole("button", { name: "Sending code…" })).toBeDisabled();

    rejectRequest?.(new ApiError(503, "SERVICE_UNAVAILABLE", "Sensitive internal detail."));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /password reset service is temporarily unavailable/i,
    );
    expect(screen.queryByText(/sensitive internal detail/i)).not.toBeInTheDocument();
  });

  it("shows OTP verification loading and sanitized backend-unavailable feedback", async () => {
    authApiMocks.login.mockResolvedValue({
      otp_required: true,
      challenge_id: "challenge-unavailable",
      expires_in: 300,
      resend_available_in: 0,
    });
    let rejectVerification: ((reason: unknown) => void) | undefined;
    authApiMocks.verifyOtp.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectVerification = reject;
      }),
    );
    const user = userEvent.setup();
    renderApplication("/login");
    await user.type(await screen.findByLabelText(/^email$/i), "teacher@domain.dev");
    await user.type(screen.getByLabelText(/password/i), "correct horse battery staple");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));
    await user.type(await screen.findByLabelText(/verification code/i), "123456");
    await user.click(screen.getByRole("button", { name: /verify and sign in/i }));
    expect(screen.getByRole("button", { name: "Verifying…" })).toBeDisabled();

    rejectVerification?.(new ApiError(503, "SERVICE_UNAVAILABLE", "Internal detail."));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /verification service is temporarily unavailable/i,
    );
    expect(screen.queryByText("Internal detail.")).not.toBeInTheDocument();
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

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /sign in to continue/i })).toBeVisible();
    });
    expect(authApiMocks.logout).toHaveBeenCalledOnce();
  });
});

describe("role routing", () => {
  const allowedCases: ReadonlyArray<[UserRole, string, RegExp, string]> = [
    ["admin", "/admin", /administration workspace/i, "Active students"],
    ["teacher", "/teacher", /teacher workspace/i, "Assigned classrooms"],
    ["student", "/student", /student portal/i, "Roll number"],
  ];

  it.each(allowedCases)(
    "allows an authenticated %s to render its role shell",
    async (role, path, heading, roleMetric) => {
      authApiMocks.restoreSession.mockResolvedValue(makeUser(role));
      renderApplication(path);
      expect(await screen.findByRole("heading", { name: heading })).toBeVisible();
      expect(screen.getByText(`${role}@school.test`)).toBeVisible();
      expect(await screen.findByText(roleMetric, {}, { timeout: 5_000 })).toBeVisible();
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

  it("offers a retry when dashboard analytics cannot be loaded", async () => {
    authApiMocks.restoreSession.mockResolvedValue(makeUser("student"));
    dashboardApiMocks.getOverview.mockRejectedValue(
      new ApiError(503, "SERVICE_UNAVAILABLE", "Unavailable"),
    );
    const user = userEvent.setup();
    renderApplication("/student");

    expect(await screen.findByRole("alert", undefined, { timeout: 5_000 })).toBeVisible();
    dashboardApiMocks.getOverview.mockResolvedValue(analyticsOverview());
    await user.click(screen.getByRole("button", { name: /retry analytics/i }));

    expect(await screen.findByText("Recent attendance trend")).toBeVisible();
  });
});
