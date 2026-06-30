import type {
  Connection,
  ReadingsResponse,
  SeriesResponse,
  StateResponse,
  SyncStatusResponse,
} from "../types";

export interface ConnectPayload {
  email: string;
  password: string;
  mfa_code?: string;
}

export interface BackfillStatusResponse {
  state: string;
  days_written: number;
  last_success_at: string | null;
  error: string | null;
}

export class ApiError extends Error {
  readonly detail: string | null;
  readonly status: number;

  constructor(method: string, path: string, response: Response, detail: string | null) {
    super(`${method} ${path} failed with ${response.status}`);
    this.name = "ApiError";
    this.detail = detail;
    this.status = response.status;
  }
}

export async function fetchState(signal?: AbortSignal): Promise<StateResponse> {
  return requestJson<StateResponse>("/api/state", {
    headers: {
      Accept: "application/json",
    },
    signal,
  });
}

export async function fetchSeries(metric: string, range: string): Promise<SeriesResponse> {
  const searchParams = new URLSearchParams({ range });
  const path = `/api/metrics/${encodeURIComponent(metric)}/series?${searchParams.toString()}`;
  return requestJson<SeriesResponse>(path, {
    headers: {
      Accept: "application/json",
    },
  });
}

export async function fetchReadings(metric: string, on: string): Promise<ReadingsResponse> {
  const searchParams = new URLSearchParams({ on });
  const path = `/api/metrics/${encodeURIComponent(metric)}/readings?${searchParams.toString()}`;
  return requestJson<ReadingsResponse>(path, {
    headers: {
      Accept: "application/json",
    },
  });
}

export async function connect(payload: ConnectPayload): Promise<Connection> {
  return requestJson<Connection>("/api/connection", {
    body: JSON.stringify(payload),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    method: "POST",
  });
}

export async function disconnect(): Promise<Connection> {
  return requestJson<Connection>("/api/connection", {
    headers: {
      Accept: "application/json",
    },
    method: "DELETE",
  });
}

export async function triggerSync(): Promise<SyncStatusResponse> {
  return requestJson<SyncStatusResponse>("/api/sync", {
    headers: {
      Accept: "application/json",
    },
    method: "POST",
  });
}

export async function triggerBackfill(): Promise<BackfillStatusResponse> {
  return requestJson<BackfillStatusResponse>("/api/backfill", {
    headers: {
      Accept: "application/json",
    },
    method: "POST",
  });
}

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(path, init);

  if (!response.ok) {
    throw new ApiError(init.method ?? "GET", path, response, await readErrorDetail(response));
  }

  return (await response.json()) as T;
}

async function readErrorDetail(response: Response): Promise<string | null> {
  const contentType = response.headers.get("Content-Type") ?? "";

  if (contentType.includes("application/json")) {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : null;
  }

  const text = await response.text();
  return text.trim() || null;
}
