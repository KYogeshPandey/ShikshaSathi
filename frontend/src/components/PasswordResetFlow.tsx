import { useEffect, useState, type FormEvent } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/authContext";
import { SlowRequestNotice } from "./SlowRequestNotice";
import type { PasswordResetGrant, PasswordResetRequestInfo } from "../types/auth";

const emailSchema = z.object({
  email: z.string().trim().min(1, "Email is required.").email("Enter a valid email address."),
});

const passwordSchema = z
  .object({
    newPassword: z
      .string()
      .min(10, "Password must be at least 10 characters.")
      .max(128, "Password must be 128 characters or fewer.")
      .regex(/[A-Za-z]/, "Password must contain at least one letter.")
      .regex(/\d/, "Password must contain at least one number."),
    confirmPassword: z.string().min(1, "Confirm your new password."),
  })
  .refine((values) => values.newPassword === values.confirmPassword, {
    message: "Passwords do not match.",
    path: ["confirmPassword"],
  });

type EmailValues = z.infer<typeof emailSchema>;
type PasswordValues = z.infer<typeof passwordSchema>;
type ResetStep = "email" | "otp" | "password" | "success";

interface PasswordResetFlowProps {
  onReturnToSignIn(resetCompleted?: boolean): void;
}

function safeResetError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "INVALID_OTP" || error.status === 401) {
      return "That verification code is incorrect or has already been used.";
    }
    if (error.code === "OTP_EXPIRED") {
      return "That verification code has expired. Request a new code.";
    }
    if (error.code === "OTP_ATTEMPTS_EXCEEDED") {
      return "Too many incorrect attempts. Request a new verification code.";
    }
    if (error.code === "INVALID_NEW_PASSWORD") {
      return "Choose at least 10 characters, including a letter and a number.";
    }
    if (error.code === "INVALID_PASSWORD_RESET_GRANT") {
      return "Your password reset authorization has expired. Request a new code.";
    }
    if (error.status === 429) {
      return "Too many password reset attempts. Please wait and try again.";
    }
    if (error.status === 0 || error.code === "NETWORK_ERROR") {
      return "The server could not be reached. Please try again shortly.";
    }
    if (error.status >= 500) {
      return "The password reset service is temporarily unavailable. Please try again shortly.";
    }
  }
  return "We could not complete that password reset step. Please try again.";
}

export function PasswordResetFlow({ onReturnToSignIn }: PasswordResetFlowProps) {
  const {
    requestPasswordReset,
    verifyPasswordResetOtp,
    resendPasswordResetOtp,
    confirmPasswordReset,
  } = useAuth();
  const [step, setStep] = useState<ResetStep>("email");
  const [submittedEmail, setSubmittedEmail] = useState("");
  const [requestInfo, setRequestInfo] = useState<PasswordResetRequestInfo | null>(null);
  const [grant, setGrant] = useState<PasswordResetGrant | null>(null);
  const [otp, setOtp] = useState("");
  const [flowError, setFlowError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [resendRemaining, setResendRemaining] = useState(0);
  const [isVerifying, setIsVerifying] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const emailForm = useForm<EmailValues>({
    resolver: zodResolver(emailSchema),
    defaultValues: { email: "" },
  });
  const passwordForm = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { newPassword: "", confirmPassword: "" },
  });

  useEffect(() => {
    if (step !== "otp" || !requestInfo) return;
    const timer = window.setInterval(() => {
      setResendRemaining((remaining) => {
        if (remaining <= 1) {
          window.clearInterval(timer);
          return 0;
        }
        return remaining - 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [requestInfo, step]);

  const onRequest = emailForm.handleSubmit(async (values) => {
    setFlowError(null);
    setStatusMessage(null);
    try {
      const email = values.email.trim();
      const result = await requestPasswordReset(email);
      setSubmittedEmail(email);
      setRequestInfo(result);
      setResendRemaining(result.resend_available_in);
      setOtp("");
      setStep("otp");
    } catch (error: unknown) {
      setFlowError(safeResetError(error));
    }
  });

  const onVerify = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!/^\d{6}$/.test(otp)) {
      setFlowError("Enter the 6-digit verification code.");
      return;
    }
    setFlowError(null);
    setStatusMessage(null);
    setIsVerifying(true);
    try {
      const result = await verifyPasswordResetOtp(submittedEmail, otp);
      setGrant(result);
      setOtp("");
      setStep("password");
    } catch (error: unknown) {
      setFlowError(safeResetError(error));
    } finally {
      setIsVerifying(false);
    }
  };

  const onResend = async () => {
    if (resendRemaining > 0) return;
    setFlowError(null);
    setStatusMessage(null);
    setIsResending(true);
    try {
      const result = await resendPasswordResetOtp(submittedEmail);
      setRequestInfo(result);
      setResendRemaining(result.resend_available_in);
      setOtp("");
      setStatusMessage("If the account is active, a new verification code has been sent.");
    } catch (error: unknown) {
      setFlowError(safeResetError(error));
    } finally {
      setIsResending(false);
    }
  };

  const onConfirm = passwordForm.handleSubmit(async (values) => {
    if (!grant) return;
    setFlowError(null);
    setStatusMessage(null);
    try {
      await confirmPasswordReset(
        grant.reset_id,
        grant.reset_token,
        values.newPassword,
        values.confirmPassword,
      );
      setStep("success");
    } catch (error: unknown) {
      setFlowError(safeResetError(error));
    }
  });

  const changeEmail = () => {
    setStep("email");
    setSubmittedEmail("");
    setRequestInfo(null);
    setGrant(null);
    setOtp("");
    setFlowError(null);
    setStatusMessage(null);
    setResendRemaining(0);
    emailForm.reset({ email: "" });
    passwordForm.reset();
  };

  if (step === "success") {
    return (
      <div className="login-form" role="status">
        <div>
          <p className="eyebrow">Password updated</p>
          <h1>Your password has been reset</h1>
          <p>Return to sign in and use your new password.</p>
        </div>
        <button
          className="button button--primary"
          onClick={() => onReturnToSignIn(true)}
          type="button"
        >
          Return to sign in
        </button>
      </div>
    );
  }

  if (step === "password" && grant) {
    return (
      <form className="login-form" onSubmit={onConfirm} noValidate>
        <div>
          <p className="eyebrow">Secure password reset</p>
          <h1>Choose a new password</h1>
          <p>The reset authorization expires in about {Math.ceil(grant.expires_in / 60)} minutes.</p>
        </div>

        <div className="field-stack">
          <label htmlFor="new-password">New password</label>
          <input
            id="new-password"
            type="password"
            autoComplete="new-password"
            aria-describedby={
              passwordForm.formState.errors.newPassword ? "new-password-error" : "password-help"
            }
            aria-invalid={Boolean(passwordForm.formState.errors.newPassword)}
            {...passwordForm.register("newPassword")}
          />
          <p className="helper-text" id="password-help">
            Use at least 10 characters, including a letter and a number.
          </p>
          {passwordForm.formState.errors.newPassword?.message ? (
            <p className="field-error" id="new-password-error">
              {passwordForm.formState.errors.newPassword.message}
            </p>
          ) : null}
        </div>

        <div className="field-stack">
          <label htmlFor="confirm-new-password">Confirm new password</label>
          <input
            id="confirm-new-password"
            type="password"
            autoComplete="new-password"
            aria-describedby={
              passwordForm.formState.errors.confirmPassword
                ? "confirm-new-password-error"
                : undefined
            }
            aria-invalid={Boolean(passwordForm.formState.errors.confirmPassword)}
            {...passwordForm.register("confirmPassword")}
          />
          {passwordForm.formState.errors.confirmPassword?.message ? (
            <p className="field-error" id="confirm-new-password-error">
              {passwordForm.formState.errors.confirmPassword.message}
            </p>
          ) : null}
        </div>

        {flowError ? <div className="form-error" role="alert">{flowError}</div> : null}
        <button
          className="button button--primary"
          disabled={passwordForm.formState.isSubmitting}
          type="submit"
        >
          {passwordForm.formState.isSubmitting ? "Updating password…" : "Update password"}
        </button>
        <div className="button-row">
          <button className="button button--quiet" onClick={changeEmail} type="button">
            Change email
          </button>
          <button
            className="button button--quiet"
            onClick={() => onReturnToSignIn(false)}
            type="button"
          >
            Back to sign in
          </button>
        </div>
        {passwordForm.formState.isSubmitting ? <SlowRequestNotice /> : null}
      </form>
    );
  }

  if (step === "otp" && requestInfo) {
    return (
      <form className="login-form" onSubmit={onVerify} noValidate>
        <div>
          <p className="eyebrow">Password reset verification</p>
          <h1>Enter your verification code</h1>
          <p>
            If an active account exists for <strong>{submittedEmail}</strong>, a 6-digit code has
            been sent.
          </p>
        </div>

        <div className="field-stack">
          <label htmlFor="password-reset-otp">Verification code</label>
          <input
            id="password-reset-otp"
            autoComplete="one-time-code"
            inputMode="numeric"
            pattern="[0-9]{6}"
            maxLength={6}
            value={otp}
            aria-describedby={flowError ? "password-reset-error" : "password-reset-otp-help"}
            aria-invalid={Boolean(flowError)}
            onChange={(event) => setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))}
          />
          <p className="helper-text" id="password-reset-otp-help">
            The code expires in about {Math.ceil(requestInfo.expires_in / 60)} minutes.
          </p>
        </div>

        {flowError ? (
          <div className="form-error" id="password-reset-error" role="alert">
            {flowError}
          </div>
        ) : null}
        {statusMessage ? <p className="success-message" role="status">{statusMessage}</p> : null}

        <button
          className="button button--primary"
          disabled={isVerifying || otp.length !== 6}
          type="submit"
        >
          {isVerifying ? "Verifying…" : "Verify code"}
        </button>
        <div className="button-row">
          <button
            className="button button--quiet"
            disabled={isResending || resendRemaining > 0}
            onClick={onResend}
            type="button"
          >
            {isResending
              ? "Sending…"
              : resendRemaining > 0
                ? `Resend in ${resendRemaining}s`
                : "Resend code"}
          </button>
          <button className="button button--quiet" onClick={changeEmail} type="button">
            Change email
          </button>
          <button
            className="button button--quiet"
            onClick={() => onReturnToSignIn(false)}
            type="button"
          >
            Back to sign in
          </button>
        </div>
        {isVerifying || isResending ? <SlowRequestNotice /> : null}
      </form>
    );
  }

  return (
    <form className="login-form" onSubmit={onRequest} noValidate>
      <div>
        <p className="eyebrow">Password help</p>
        <h1>Reset your password</h1>
        <p>Enter your registered email address.</p>
      </div>

      <div className="field-stack">
        <label htmlFor="password-reset-email">Email</label>
        <input
          id="password-reset-email"
          autoComplete="email"
          aria-describedby={
            emailForm.formState.errors.email ? "password-reset-email-error" : undefined
          }
          aria-invalid={Boolean(emailForm.formState.errors.email)}
          {...emailForm.register("email")}
        />
        {emailForm.formState.errors.email?.message ? (
          <p className="field-error" id="password-reset-email-error">
            {emailForm.formState.errors.email.message}
          </p>
        ) : null}
      </div>

      {flowError ? <div className="form-error" role="alert">{flowError}</div> : null}
      <button
        className="button button--primary"
        disabled={emailForm.formState.isSubmitting}
        type="submit"
      >
        {emailForm.formState.isSubmitting ? "Sending code…" : "Send verification code"}
      </button>
      <button
        className="button button--quiet"
        onClick={() => onReturnToSignIn(false)}
        type="button"
      >
        Back to sign in
      </button>
      {emailForm.formState.isSubmitting ? <SlowRequestNotice /> : null}
    </form>
  );
}
