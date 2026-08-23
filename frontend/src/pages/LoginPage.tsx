import { useEffect, useState, type FormEvent } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate } from "react-router-dom";
import { z } from "zod";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/authContext";
import { LoadingScreen } from "../components/LoadingScreen";
import { SlowRequestNotice } from "../components/SlowRequestNotice";
import { homePathForRole } from "../routes/config";
import { isOtpChallenge, type OtpChallengeInfo } from "../types/auth";

const loginSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Email is required.")
    .email("Enter a valid email address."),
  password: z
    .string()
    .min(1, "Password is required.")
    .max(128, "Password must be 128 characters or fewer."),
});

type LoginFormValues = z.infer<typeof loginSchema>;

function safeLoginError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.code === "INVALID_CREDENTIALS") {
      return "Incorrect email or password.";
    }
    if (error.status === 429) {
      return "Too many login attempts. Please wait and try again.";
    }
    if (error.status === 0 || error.code === "NETWORK_ERROR") {
      return "The server could not be reached. Please try again shortly.";
    }
    if (error.status >= 500) {
      return "The server is temporarily unavailable. Please try again shortly.";
    }
  }
  return "We could not sign you in. Please try again.";
}

function safeOtpError(error: unknown): string {
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
    if (error.code === "OTP_RESEND_COOLDOWN" || error.status === 429) {
      return "Please wait before requesting another verification code.";
    }
    if (error.status === 0 || error.code === "NETWORK_ERROR") {
      return "The server could not be reached. Please try again shortly.";
    }
    if (error.status >= 500) {
      return "The verification service is temporarily unavailable. Please try again shortly.";
    }
  }
  return "We could not verify that code. Please try again.";
}

export function LoginPage() {
  const { status, user, login, verifyOtp, resendOtp } = useAuth();
  const navigate = useNavigate();
  const [challenge, setChallenge] = useState<OtpChallengeInfo | null>(null);
  const [otp, setOtp] = useState("");
  const [otpError, setOtpError] = useState<string | null>(null);
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const [resendRemaining, setResendRemaining] = useState(0);
  const [isVerifying, setIsVerifying] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const {
    register,
    handleSubmit,
    setError,
    clearErrors,
    getValues,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  useEffect(() => {
    clearErrors("root");
  }, [clearErrors]);

  useEffect(() => {
    if (!challenge) return;
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
  }, [challenge]);

  if (status === "loading") {
    return <LoadingScreen />;
  }
  if (status === "authenticated" && user) {
    return <Navigate to={homePathForRole(user.role)} replace />;
  }

  const onSubmit = handleSubmit(async (values) => {
    clearErrors("root");
    try {
      const currentUser = await login(values);
      if (isOtpChallenge(currentUser)) {
        setChallenge(currentUser);
        setResendRemaining(currentUser.resend_available_in);
        setOtp("");
        setOtpError(null);
        setResendMessage(null);
        return;
      }
      navigate(homePathForRole(currentUser.role), { replace: true });
    } catch (error: unknown) {
      setError("root", { message: safeLoginError(error) });
    }
  });

  const onVerify = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!challenge || !/^\d{6}$/.test(otp)) {
      setOtpError("Enter the 6-digit verification code.");
      return;
    }
    setOtpError(null);
    setResendMessage(null);
    setIsVerifying(true);
    try {
      const currentUser = await verifyOtp(challenge.challenge_id, otp);
      navigate(homePathForRole(currentUser.role), { replace: true });
    } catch (error: unknown) {
      setOtpError(safeOtpError(error));
    } finally {
      setIsVerifying(false);
    }
  };

  const onResend = async () => {
    if (!challenge || resendRemaining > 0) return;
    setOtpError(null);
    setResendMessage(null);
    setIsResending(true);
    try {
      const replacement = await resendOtp(challenge.challenge_id);
      setChallenge(replacement);
      setOtp("");
      setResendRemaining(replacement.resend_available_in);
      setResendMessage("A new verification code has been sent.");
    } catch (error: unknown) {
      setOtpError(safeOtpError(error));
    } finally {
      setIsResending(false);
    }
  };

  const changeAccount = () => {
    setChallenge(null);
    setOtp("");
    setOtpError(null);
    setResendMessage(null);
    setResendRemaining(0);
    reset({ email: "", password: "" });
    clearErrors("root");
  };

  return (
    <main className="login-page">
      <section className="login-intro" aria-labelledby="login-heading">
        <a className="brand brand--inverse" href="/">
          <span className="brand-mark" aria-hidden="true">S</span>
          <span>ShikshaSathi</span>
        </a>
        <div className="login-intro-content">
          <p className="eyebrow">Learning, connected</p>
          <h2 id="login-heading">One calm place for your school day.</h2>
          <p className="intro-copy">
            Sign in to enter the workspace assigned to your school role.
          </p>
        </div>
        <p className="workspace-label workspace-label--dark">Secure role-based access</p>
      </section>

      <section className="login-panel" aria-label="Sign in">
        <a className="brand login-panel-brand" href="/">
          <span className="brand-mark" aria-hidden="true">S</span>
          <span>ShikshaSathi</span>
        </a>
        {challenge ? (
          <form className="login-form" key="otp" onSubmit={onVerify} noValidate>
            <div>
              <p className="eyebrow">Email verification</p>
              <h1>Enter your sign-in code</h1>
              <p>
                We sent a 6-digit code to <strong>{getValues("email")}</strong>.
              </p>
            </div>

            <div className="field-stack">
              <label htmlFor="otp">Verification code</label>
              <input
                id="otp"
                autoComplete="one-time-code"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                value={otp}
                aria-describedby={otpError ? "otp-error" : "otp-help"}
                aria-invalid={Boolean(otpError)}
                onChange={(event) => setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))}
              />
              <p className="helper-text" id="otp-help">
                The code expires in about {Math.ceil(challenge.expires_in / 60)} minutes.
              </p>
            </div>

            {otpError ? (
              <div className="form-error" id="otp-error" role="alert">{otpError}</div>
            ) : null}
            {resendMessage ? (
              <p className="success-message" role="status">{resendMessage}</p>
            ) : null}

            <button
              className="button button--primary"
              disabled={isVerifying || otp.length !== 6}
              type="submit"
            >
              {isVerifying ? "Verifying…" : "Verify and sign in"}
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
              <button className="button button--quiet" onClick={changeAccount} type="button">
                Change account
              </button>
            </div>
            {isVerifying || isResending ? <SlowRequestNotice /> : null}
          </form>
        ) : (
        <form className="login-form" key="credentials" onSubmit={onSubmit} noValidate>
          <div>
            <p className="eyebrow">Welcome back</p>
            <h1>Sign in to continue</h1>
            <p>Enter your registered email address.</p>
          </div>

          <div className="field-stack">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              autoComplete="username"
              aria-describedby={errors.email ? "email-error" : undefined}
              aria-invalid={Boolean(errors.email)}
              {...register("email")}
            />
            {errors.email?.message && (
              <p className="field-error" id="email-error">{errors.email.message}</p>
            )}
          </div>

          <div className="field-stack">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              aria-describedby={errors.password ? "password-error" : undefined}
              aria-invalid={Boolean(errors.password)}
              {...register("password")}
            />
            {errors.password?.message && (
              <p className="field-error" id="password-error">{errors.password.message}</p>
            )}
          </div>

          {errors.root?.message && (
            <div className="form-error" role="alert">
              {errors.root.message}
            </div>
          )}

          <button className="button button--primary" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Signing in…" : "Sign in"}
          </button>
          {isSubmitting ? <SlowRequestNotice /> : null}
        </form>
        )}
      </section>
    </main>
  );
}
