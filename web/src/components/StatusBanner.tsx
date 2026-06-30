import { useEffect, type ReactNode } from "react";

export type StatusBannerVariant = "loading" | "success" | "note";

interface StatusBannerProps {
  autoDismissMs?: number;
  message: ReactNode;
  onDismiss?: () => void;
  variant: StatusBannerVariant;
}

export function StatusBanner({
  autoDismissMs = 4000,
  message,
  onDismiss,
  variant,
}: StatusBannerProps) {
  useEffect(() => {
    if (variant !== "success" || !onDismiss) {
      return;
    }

    const timer = window.setTimeout(onDismiss, autoDismissMs);

    return () => window.clearTimeout(timer);
  }, [autoDismissMs, message, onDismiss, variant]);

  return (
    <div
      aria-busy={variant === "loading" ? true : undefined}
      aria-live="polite"
      className={`status-banner status-banner--${variant}`}
      role="status"
    >
      {variant !== "loading" ? <span aria-hidden="true" className="status-banner__dot" /> : null}
      <span className="status-banner__message">{message}</span>
      {variant === "note" && onDismiss ? (
        <button
          aria-label="Dismiss status"
          className="status-banner__close"
          onClick={onDismiss}
          type="button"
        >
          <span aria-hidden="true">{"\u00d7"}</span>
        </button>
      ) : null}
      {variant === "loading" ? (
        <span aria-hidden="true" className="status-banner__progress">
          <span />
        </span>
      ) : null}
    </div>
  );
}
