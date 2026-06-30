export type TrendAgg = "last" | "sum";

export type ConnectionStatus = "connected" | "disconnected" | "needs_mfa";
export type SyncState = "idle" | "syncing" | "running" | "error" | "not_connected";

export interface Freshness {
  last_success_at: string | null;
  next_scheduled_at: string | null;
}

export interface Connection {
  state: ConnectionStatus;
}

export interface SleepValue {
  score: number | null;
  score_label: string | null;
  hours: number | null;
  duration_str: string | null;
  hrv_overnight: number | null;
  start_local: string | null;
  end_local: string | null;
  in_bed_before_midnight: boolean | null;
}

export interface HrvValue {
  last_night_avg: number | null;
  weekly_avg: number | null;
  status: string | null;
  baseline_low: number | null;
  baseline_high: number | null;
  feedback: string | null;
}

export interface RestingHrValue {
  bpm: number | null;
}

export interface StepsValue {
  total: number | null;
}

export interface StressValue {
  avg: number | null;
  label: string | null;
}

export interface BodyBatteryValue {
  high: number | null;
  low: number | null;
  most_recent: number | null;
  charged: number | null;
  drained: number | null;
}

export interface Vo2MaxValue {
  value: number | null;
}

export interface FitnessAgeValue {
  fitness_age: number | null;
  chronological_age: number | null;
  achievable: number | null;
}

export interface TrainingReadinessValue {
  score: number | null;
  level: string | null;
  feedback: string | null;
}

export interface RunningValue {
  km: number | null;
  runs: number | null;
  week_start: string | null;
  week_end: string | null;
}

export interface MetricValueMap {
  sleep: SleepValue;
  hrv: HrvValue;
  resting_hr: RestingHrValue;
  steps: StepsValue;
  stress: StressValue;
  body_battery: BodyBatteryValue;
  vo2_max: Vo2MaxValue;
  fitness_age: FitnessAgeValue;
  training_readiness: TrainingReadinessValue;
  running: RunningValue;
}

export type MetricKey = keyof MetricValueMap;

export interface StateMetric<K extends MetricKey = MetricKey> {
  value: MetricValueMap[K];
  label: string;
  unit: string | null;
  has_readings: boolean;
}

export type StateMetrics = {
  [K in MetricKey]: StateMetric<K>;
};

export interface StateResponse {
  date: string;
  metrics: StateMetrics;
  freshness: Freshness;
  connection: Connection;
}

export interface ContractMetric<K extends MetricKey = MetricKey> {
  key: K;
  label: string;
  unit: string | null;
  has_readings: boolean;
  agg: TrendAgg;
}

export interface MetricsResponse {
  metrics: ContractMetric[];
}

export interface SeriesPoint {
  at: string;
  value: number;
}

export interface SeriesResponse {
  metric: MetricKey;
  range: string;
  points: SeriesPoint[];
}

export interface MetricReading {
  at: string;
  value: number;
  detail: Record<string, string | number | boolean | null>;
}

export interface ReadingsResponse {
  metric: MetricKey;
  on: string;
  readings: MetricReading[];
  factors: Record<string, string | number | boolean | null> | null;
}

export interface SyncStatusResponse {
  state: SyncState;
  last_success_at: string | null;
  error: string | null;
}
