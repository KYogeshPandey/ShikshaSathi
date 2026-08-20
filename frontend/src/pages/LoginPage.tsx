import { useEffect } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate } from "react-router-dom";
import { z } from "zod";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/authContext";
import { LoadingScreen } from "../components/LoadingScreen";
import { homePathForRole } from "../routes/config";

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
  }
  return "We could not sign you in. Please try again.";
}

export function LoginPage() {
  const { status, user, login } = useAuth();
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    setError,
    clearErrors,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  useEffect(() => {
    clearErrors("root");
  }, [clearErrors]);

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
      navigate(homePathForRole(currentUser.role), { replace: true });
    } catch (error: unknown) {
      setError("root", { message: safeLoginError(error) });
    }
  });

  return (
    <main className="login-page">
      <section className="login-intro" aria-labelledby="login-heading">
        <a className="brand brand--inverse" href="/">
          <span className="brand-mark" aria-hidden="true">S</span>
          <span>ShikshaSathi</span>
        </a>
        <div className="login-intro-content">
          <p className="eyebrow">Learning, connected</p>
          <h1 id="login-heading">One calm place for your school day.</h1>
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
        <form className="login-form" onSubmit={onSubmit} noValidate>
          <div>
            <p className="eyebrow">Welcome back</p>
            <h2>Sign in to continue</h2>
            <p>Use the email address provided by your school.</p>
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
        </form>
      </section>
    </main>
  );
}
