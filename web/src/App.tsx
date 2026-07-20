import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { MetricModal } from "./components/MetricModal";
import { StatusBanner, type StatusBannerVariant } from "./components/StatusBanner";
import {
  ApiError,
  connect,
  disconnect,
  fetchState,
  triggerBackfill,
  triggerSync,
  type ConnectPayload,
} from "./data/api";
import {
  AVERAGE_LABELS,
  OPTIMAL_LABELS,
  metricDisplaySpecs,
  type MetricDisplaySpec,
  type MetricTone,
  type NumberFormat,
} from "./data/metricRegistry";
import type { MetricKey, StateMetric, StateResponse } from "./types";

const numberFormatter = new Intl.NumberFormat("en-US");
const decimalFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
  minimumFractionDigits: 1,
});

type MetricBadgeStyle = CSSProperties & {
  "--metric-badge-tone": string;
};

interface StatusBannerState {
  id: number;
  message: string;
  variant: StatusBannerVariant;
}

interface DashboardMetricCard {
  metric: StateMetric;
  spec: MetricDisplaySpec;
}

function readField(value: object, field: string): unknown {
  return (value as Record<string, unknown>)[field];
}

function formatPrimitive(value: unknown, format?: NumberFormat): string | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  if (typeof value === "number") {
    return format === "decimal1" ? decimalFormatter.format(value) : numberFormatter.format(value);
  }

  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }

  return String(value);
}

function toTitleCase(value: string): string {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(" ");
}

function formatElapsed(fromIso: string | null, nowMs: number): string {
  if (!fromIso) {
    return "sync pending";
  }

  const fromMs = new Date(fromIso).getTime();

  if (Number.isNaN(fromMs)) {
    return "sync time unavailable";
  }

  const elapsedSeconds = Math.max(0, Math.floor((nowMs - fromMs) / 1000));

  if (elapsedSeconds < 60) {
    return `synced ${elapsedSeconds}s ago`;
  }

  const elapsedMinutes = Math.floor(elapsedSeconds / 60);

  if (elapsedMinutes < 60) {
    return `synced ${elapsedMinutes}m ago`;
  }

  const hours = Math.floor(elapsedMinutes / 60);
  const minutes = elapsedMinutes % 60;

  if (hours < 24) {
    return minutes > 0 ? `synced ${hours}h ${minutes}m ago` : `synced ${hours}h ago`;
  }

  const days = Math.floor(hours / 24);
  const remainderHours = hours % 24;

  return remainderHours > 0 ? `synced ${days}d ${remainderHours}h ago` : `synced ${days}d ago`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value}T00:00:00`));
}

function describeApiError(unknownError: unknown, fallback: string): string {
  if (unknownError instanceof ApiError) {
    if (unknownError.status === 429) {
      return "Garmin is cooling down requests right now. Wait a bit, then try again.";
    }

    if (unknownError.status === 503) {
      return unknownError.detail
        ? `TrackHealth needs a runtime setting before this can continue. ${unknownError.detail}`
        : "TrackHealth needs a runtime setting before this can continue.";
    }

    return unknownError.detail ? `${fallback} ${unknownError.detail}` : fallback;
  }

  return unknownError instanceof Error ? unknownError.message : fallback;
}

const TONE_VAR: Record<MetricTone, string> = {
  positive: "var(--positive)",
  average: "var(--risk-medium)",
  alert: "var(--accent)",
};

function qualitativeTone(
  value: string | null,
  tones?: Partial<Record<string, MetricTone>>,
): string {
  if (!value) {
    return "var(--secondary)";
  }

  const normalized = value.trim().toLowerCase();
  const perMetric = tones?.[normalized];
  if (perMetric) {
    return TONE_VAR[perMetric];
  }
  if (OPTIMAL_LABELS.has(normalized)) {
    return "var(--positive)";
  }
  if (AVERAGE_LABELS.has(normalized)) {
    return "var(--risk-medium)";
  }
  return "var(--accent)";
}

function secondaryText(metric: StateMetric, spec: MetricDisplaySpec): string {
  const parts = spec.secondary
    .map((item) => {
      const raw = readField(metric.value, item.field);
      const formatted = formatPrimitive(raw, item.format);

      if (!formatted) {
        return null;
      }

      const prefix = item.prefix ?? "";
      const unit = item.unit ? ` ${item.unit}` : "";
      const suffix = item.suffix ? ` ${item.suffix}` : "";

      return `${prefix}${formatted}${unit}${suffix}`;
    })
    .filter(Boolean);

  return parts.length > 0 ? parts.join(" / ") : "No contract value";
}

function MetricCard({
  metric,
  onOpen,
  spec,
}: {
  metric: StateMetric;
  onOpen: () => void;
  spec: MetricDisplaySpec;
}) {
  const primaryValue = formatPrimitive(readField(metric.value, spec.trendField), spec.valueFormat) ?? "--";
  const qualitativeRaw = spec.qualitativeField
    ? formatPrimitive(readField(metric.value, spec.qualitativeField))
    : null;
  const qualitativeLabel = qualitativeRaw ? toTitleCase(qualitativeRaw) : null;
  const tone = qualitativeTone(qualitativeLabel, spec.tones);
  const badgeStyle: MetricBadgeStyle = {
    "--metric-badge-tone": tone,
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onOpen();
    }
  };

  return (
    <article
      className="metric-card metric-card--interactive"
      onClick={onOpen}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
    >
      <div className="metric-card__top">
        <div>
          <p className="metric-card__section">{spec.section}</p>
          <h3>{metric.label || spec.label}</h3>
        </div>
        {qualitativeLabel ? (
          <span className="metric-card__badge" style={badgeStyle}>
            <span aria-hidden="true" className="metric-card__dot" />
            {qualitativeLabel}
          </span>
        ) : null}
      </div>

      <div className="metric-card__stat">
        <p className="metric-card__value">
          <span>{primaryValue}</span>
          {metric.unit ? <span className="metric-card__unit">{metric.unit}</span> : null}
        </p>
        <p className="metric-card__detail">{secondaryText(metric, spec)}</p>
      </div>
    </article>
  );
}

function useNow() {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => window.clearInterval(timer);
  }, []);

  return now;
}

function ConnectScreen({
  initialNeedsMfa,
  onConnected,
  reason,
}: {
  initialNeedsMfa: boolean;
  onConnected: () => Promise<void>;
  reason: "first_run" | "expired";
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [needsMfa, setNeedsMfa] = useState(initialNeedsMfa);
  const [message, setMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setMessage(null);

    const payload: ConnectPayload = {
      email,
      password,
    };

    if (needsMfa) {
      payload.mfa_code = mfaCode;
    }

    try {
      const connection = await connect(payload);

      if (connection.state === "needs_mfa") {
        setNeedsMfa(true);
        setMessage("Enter the Garmin verification code to finish connecting.");
        return;
      }

      if (connection.state === "connected") {
        setMessage("Opening dashboard...");
        await onConnected();
        return;
      }

      setMessage("Garmin is still disconnected. Check the credentials and try again.");
    } catch (unknownError) {
      setMessage(describeApiError(unknownError, "Garmin connection did not complete."));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="app-shell">
      <section className="connection-screen" aria-labelledby="connection-title">
        <div className="connection-screen__copy">
          <p className="eyebrow">{reason === "expired" ? "Session expired" : "First run"}</p>
          <h1 id="connection-title">
            {reason === "expired" ? "Reconnect Garmin account" : "Connect Garmin account"}
          </h1>
          <p className="connection-screen__lede">
            {reason === "expired"
              ? "Your Garmin session expired, so syncing is paused. Sign in again to resume. Your data stays on this Instance."
              : "TrackHealth uses this once to create the encrypted Garmin token for this private Instance."}
          </p>
        </div>

        <form className="connect-form" onSubmit={handleSubmit}>
          <div className="connect-form__field">
            <label htmlFor="garmin-email">Garmin email</label>
            <input
              autoComplete="username"
              id="garmin-email"
              name="email"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </div>

          <div className="connect-form__field">
            <label htmlFor="garmin-password">Garmin password</label>
            <input
              autoComplete="current-password"
              id="garmin-password"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </div>

          {needsMfa ? (
            <div className="connect-form__field">
              <label htmlFor="garmin-mfa">MFA code</label>
              <input
                autoComplete="one-time-code"
                id="garmin-mfa"
                inputMode="numeric"
                name="mfa_code"
                onChange={(event) => setMfaCode(event.target.value)}
                required
                type="text"
                value={mfaCode}
              />
            </div>
          ) : null}

          {message ? (
            <p className="form-message" role="status">
              {message}
            </p>
          ) : null}

          <button className="control-button control-button--primary" disabled={isSubmitting} type="submit">
            {isSubmitting
              ? "Connecting"
              : needsMfa
                ? "Submit code"
                : reason === "expired"
                  ? "Reconnect Garmin"
                  : "Connect Garmin"}
          </button>
        </form>
      </section>
    </main>
  );
}

export function App() {
  const [state, setState] = useState<StateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openMetricKey, setOpenMetricKey] = useState<MetricKey | null>(null);
  const [statusBanner, setStatusBanner] = useState<StatusBannerState | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const lastOpenCardRef = useRef<DashboardMetricCard | null>(null);
  const statusBannerIdRef = useRef(0);
  const now = useNow();

  const showStatusBanner = useCallback((variant: StatusBannerVariant, message: string) => {
    statusBannerIdRef.current += 1;
    setStatusBanner({ id: statusBannerIdRef.current, message, variant });
  }, []);

  const showSuccessStatusBannerUnlessNote = useCallback((message: string) => {
    setStatusBanner((currentBanner) => {
      if (currentBanner?.variant === "note") {
        return currentBanner;
      }

      statusBannerIdRef.current += 1;
      return { id: statusBannerIdRef.current, message, variant: "success" };
    });
  }, []);

  const dismissStatusBanner = useCallback(() => {
    setStatusBanner(null);
  }, []);

  const refreshState = useCallback(async (signal?: AbortSignal) => {
    const nextState = await fetchState(signal);
    setState(nextState);
    setError(null);
    return nextState;
  }, []);

  const refreshStateWithBanner = useCallback(
    async (fallback: string) => {
      try {
        await refreshState();
      } catch (unknownError) {
        showStatusBanner("note", describeApiError(unknownError, fallback));
      }
    },
    [refreshState, showStatusBanner],
  );

  const startConnectedBackgroundSync = useCallback(() => {
    showStatusBanner("loading", "Syncing your history\u2026");

    void triggerSync()
      .then((sync) => {
        if (sync.state === "not_connected") {
          showStatusBanner("note", "Connect Garmin before syncing.");
        } else if (sync.error) {
          showStatusBanner("note", `Sync finished with a note: ${sync.error}`);
        }
      })
      .catch((unknownError: unknown) => {
        showStatusBanner("note", describeApiError(unknownError, "Sync did not start."));
      })
      .finally(() => {
        void refreshStateWithBanner("Sync finished, but state did not refresh.");
      });

    void triggerBackfill()
      .then((backfill) => {
        if (backfill.error) {
          showStatusBanner("note", `History sync finished with a note: ${backfill.error}`);
          return;
        }

        showSuccessStatusBannerUnlessNote("History synced");
      })
      .catch((unknownError: unknown) => {
        showStatusBanner("note", describeApiError(unknownError, "History sync did not start."));
      })
      .finally(() => {
        void refreshStateWithBanner("History sync finished, but state did not refresh.");
      });
  }, [
    refreshStateWithBanner,
    showStatusBanner,
    showSuccessStatusBannerUnlessNote,
  ]);

  const handleConnected = useCallback(async () => {
    await refreshState();
    startConnectedBackgroundSync();
  }, [refreshState, startConnectedBackgroundSync]);

  useEffect(() => {
    const controller = new AbortController();

    refreshState(controller.signal)
      .catch((unknownError: unknown) => {
        if (unknownError instanceof DOMException && unknownError.name === "AbortError") {
          return;
        }

        setError(describeApiError(unknownError, "Unable to load state."));
      });

    return () => controller.abort();
  }, [refreshState]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void refreshStateWithBanner("State did not refresh after returning to the dashboard.");
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [refreshStateWithBanner]);

  const handleSyncNow = async () => {
    setIsSyncing(true);
    showStatusBanner("loading", "Syncing now\u2026");

    try {
      const sync = await triggerSync();

      if (sync.state === "not_connected") {
        showStatusBanner("note", "Connect Garmin before syncing.");
      } else if (sync.error) {
        showStatusBanner("note", `Sync finished with a note: ${sync.error}`);
      } else {
        showStatusBanner("success", "Sync finished.");
      }

      await refreshStateWithBanner("Sync finished, but state did not refresh.");
    } catch (unknownError) {
      showStatusBanner("note", describeApiError(unknownError, "Sync did not start."));
    } finally {
      setIsSyncing(false);
    }
  };

  const handleDisconnect = async () => {
    setIsDisconnecting(true);
    dismissStatusBanner();

    try {
      const connection = await disconnect();
      setOpenMetricKey(null);
      setState((currentState) => (currentState ? { ...currentState, connection } : currentState));
    } catch (unknownError) {
      showStatusBanner("note", describeApiError(unknownError, "Disconnect did not complete."));
    } finally {
      setIsDisconnecting(false);
    }
  };

  const cards = useMemo(() => {
    if (!state) {
      return [];
    }

    const nextCards: DashboardMetricCard[] = [];

    for (const spec of metricDisplaySpecs) {
      const metric = state.metrics[spec.key as MetricKey];

      if (metric) {
        nextCards.push({ metric: metric as StateMetric, spec });
      }
    }

    return nextCards;
  }, [state]);

  const currentOpenCard = useMemo(() => {
    if (!openMetricKey) {
      return null;
    }

    return cards.find(({ spec }) => spec.key === openMetricKey) ?? null;
  }, [cards, openMetricKey]);

  useEffect(() => {
    if (currentOpenCard) {
      lastOpenCardRef.current = currentOpenCard;
    }
  }, [currentOpenCard]);

  const openCard =
    openMetricKey && currentOpenCard
      ? currentOpenCard
      : openMetricKey && lastOpenCardRef.current?.spec.key === openMetricKey
        ? lastOpenCardRef.current
        : null;

  if (error) {
    return (
      <main className="app-shell">
        <section className="state-panel" role="alert">
          <p className="eyebrow">TrackHealth OS</p>
          <h1>State unavailable</h1>
          <p>{error}</p>
        </section>
      </main>
    );
  }

  if (!state) {
    return (
      <main className="app-shell">
        <section className="state-panel" aria-live="polite">
          <p className="eyebrow">TrackHealth OS</p>
          <h1>Loading contract state</h1>
        </section>
      </main>
    );
  }

  if (state.connection.state !== "connected") {
    return (
      <ConnectScreen
        initialNeedsMfa={state.connection.state === "needs_mfa"}
        onConnected={handleConnected}
        reason={state.connection.state === "expired" ? "expired" : "first_run"}
      />
    );
  }

  return (
    <main className="app-shell">
      <header className="dashboard-header">
        <div className="dashboard-header__copy">
          <p className="eyebrow">TrackHealth OS</p>
          <h1>Daily Readiness Panel</h1>
          <p className="dashboard-header__meta">
            {formatDate(state.date)} / {formatElapsed(state.freshness.last_success_at, now)}
          </p>
        </div>

        <div className="sync-cluster">
          <div className="sync-rail" aria-label="Connection summary">
            <div>
              <span>connection</span>
              <strong>{toTitleCase(state.connection.state)}</strong>
            </div>
            <div>
              <span>metrics</span>
              <strong>{cards.length}</strong>
            </div>
            <div>
              <span>next sync</span>
              <strong>
                {state.freshness.next_scheduled_at
                  ? new Intl.DateTimeFormat("en-US", {
                      hour: "2-digit",
                      minute: "2-digit",
                    }).format(new Date(state.freshness.next_scheduled_at))
                  : "not set"}
              </strong>
            </div>
            <div className="sync-rail__actions">
              <button
                className="control-button control-button--primary"
                disabled={isSyncing || isDisconnecting}
                onClick={handleSyncNow}
                type="button"
              >
                {isSyncing ? "Syncing" : "Sync now"}
              </button>
              <button
                className="control-button"
                disabled={isSyncing || isDisconnecting}
                onClick={handleDisconnect}
                type="button"
              >
                {isDisconnecting ? "Disconnecting" : "Disconnect"}
              </button>
            </div>
          </div>
        </div>
      </header>

      {statusBanner ? (
        <StatusBanner
          key={statusBanner.id}
          message={statusBanner.message}
          onDismiss={dismissStatusBanner}
          variant={statusBanner.variant}
        />
      ) : null}

      <section className="metrics-section" aria-labelledby="metrics-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Current Snapshot</p>
            <h2 id="metrics-title">Health Metrics</h2>
          </div>
          <p className="section-heading__date">{state.date}</p>
        </div>

        <div className="metrics-grid">
          {cards.map(({ metric, spec }) => (
            <MetricCard key={spec.key} metric={metric} onOpen={() => setOpenMetricKey(spec.key)} spec={spec} />
          ))}
        </div>
      </section>

      {openCard ? (
        <MetricModal
          dashboardDate={state.date}
          key={openCard.spec.key}
          metric={openCard.metric}
          onClose={() => setOpenMetricKey(null)}
          spec={openCard.spec}
        />
      ) : null}
    </main>
  );
}
