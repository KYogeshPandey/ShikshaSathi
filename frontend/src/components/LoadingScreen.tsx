import { SlowRequestNotice } from "./SlowRequestNotice";

interface LoadingScreenProps {
  message?: string;
}

export function LoadingScreen({
  message = "Restoring your session…",
}: LoadingScreenProps) {
  return (
    <main className="centered-page" aria-busy="true" aria-live="polite">
      <div className="loading-card">
        <div className="loading-primary">
          <span className="spinner" aria-hidden="true" />
          <p>{message}</p>
        </div>
        <SlowRequestNotice />
      </div>
    </main>
  );
}
