import { useEffect, useState } from "react";

export const SLOW_REQUEST_NOTICE_DELAY_MS = 3_000;

export function SlowRequestNotice() {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setIsVisible(true), SLOW_REQUEST_NOTICE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, []);

  if (!isVisible) return null;

  return (
    <p className="slow-request-notice" role="status">
      The server is waking up. This may take a few moments.
    </p>
  );
}
