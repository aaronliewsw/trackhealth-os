import type { MetricKey, MetricValueMap, TrendAgg } from "../types";

type ValueField<K extends MetricKey> = Extract<keyof MetricValueMap[K], string>;

export type NumberFormat = "integer" | "decimal1";
export type MetricTone = "positive" | "average" | "alert";

export interface SecondaryField<K extends MetricKey> {
  field: ValueField<K>;
  prefix?: string;
  suffix?: string;
  unit?: string;
  format?: NumberFormat;
}

export type MetricDisplaySpec = {
  [K in MetricKey]: {
    key: K;
    label: string;
    unit: string | null;
    hasReadings: boolean;
    agg: TrendAgg;
    trendField: ValueField<K>;
    section: string;
    valueFormat?: NumberFormat;
    qualitativeField?: ValueField<K>;
    tones?: Partial<Record<string, MetricTone>>;
    secondary: readonly SecondaryField<K>[];
  };
}[MetricKey];

export const OPTIMAL_LABELS = new Set(["excellent", "good", "balanced"]);
export const AVERAGE_LABELS = new Set(["moderate", "fair"]);

export const metricDisplaySpecs = [
  {
    key: "sleep",
    label: "Sleep Score",
    unit: null,
    hasReadings: false,
    agg: "last",
    trendField: "score",
    section: "Last night",
    valueFormat: "integer",
    qualitativeField: "score_label",
    tones: { excellent: "positive", good: "positive", fair: "average", poor: "alert" },
    secondary: [
      { field: "duration_str", suffix: "sleep" },
      { field: "hrv_overnight", prefix: "HRV ", unit: "ms", format: "integer" },
    ],
  },
  {
    key: "hrv",
    label: "HRV",
    unit: "ms",
    hasReadings: true,
    agg: "last",
    trendField: "last_night_avg",
    section: "Last night",
    valueFormat: "integer",
    qualitativeField: "status",
    tones: { balanced: "positive", unbalanced: "alert", low: "alert", poor: "alert" },
    secondary: [
      { field: "weekly_avg", prefix: "weekly avg ", unit: "ms", format: "integer" },
      { field: "feedback" },
    ],
  },
  {
    key: "resting_hr",
    label: "Resting HR",
    unit: "bpm",
    hasReadings: false,
    agg: "last",
    trendField: "bpm",
    section: "Wake summary",
    valueFormat: "integer",
    secondary: [{ field: "bpm", prefix: "current resting baseline ", unit: "bpm", format: "integer" }],
  },
  {
    key: "steps",
    label: "Steps",
    unit: "steps",
    hasReadings: true,
    agg: "sum",
    trendField: "total",
    section: "Today",
    valueFormat: "integer",
    secondary: [{ field: "total", prefix: "daily total ", unit: "steps", format: "integer" }],
  },
  {
    key: "stress",
    label: "Stress",
    unit: null,
    hasReadings: true,
    agg: "last",
    trendField: "avg",
    section: "Today",
    valueFormat: "integer",
    qualitativeField: "label",
    tones: { low: "positive", moderate: "average", high: "alert", "very high": "alert" },
    secondary: [{ field: "avg", prefix: "daily average ", format: "integer" }],
  },
  {
    key: "body_battery",
    label: "Body Battery",
    unit: null,
    hasReadings: true,
    agg: "last",
    trendField: "most_recent",
    section: "Current",
    valueFormat: "integer",
    secondary: [
      { field: "high", prefix: "high ", format: "integer" },
      { field: "low", prefix: "low ", format: "integer" },
      { field: "charged", prefix: "charged ", format: "integer" },
      { field: "drained", prefix: "drained ", format: "integer" },
    ],
  },
  {
    key: "vo2_max",
    label: "VO2 Max",
    unit: "ml/kg/min",
    hasReadings: false,
    agg: "last",
    trendField: "value",
    section: "Cardio fitness",
    valueFormat: "decimal1",
    secondary: [{ field: "value", prefix: "estimate ", unit: "ml/kg/min", format: "decimal1" }],
  },
  {
    key: "fitness_age",
    label: "Fitness Age",
    unit: "yrs",
    hasReadings: false,
    agg: "last",
    trendField: "fitness_age",
    section: "Cardio fitness",
    valueFormat: "decimal1",
    secondary: [
      { field: "chronological_age", prefix: "actual ", unit: "yrs", format: "integer" },
      { field: "achievable", prefix: "achievable ", unit: "yrs", format: "decimal1" },
    ],
  },
  {
    key: "training_readiness",
    label: "Training Readiness",
    unit: null,
    hasReadings: false,
    agg: "last",
    trendField: "score",
    section: "Today",
    valueFormat: "integer",
    qualitativeField: "level",
    tones: { low: "alert", moderate: "average", high: "positive", maximum: "positive", prime: "positive", ready: "positive" },
    secondary: [{ field: "feedback" }],
  },
  {
    key: "running",
    label: "Running",
    unit: "km",
    hasReadings: false,
    agg: "last",
    trendField: "km",
    section: "Week to date",
    valueFormat: "decimal1",
    secondary: [
      { field: "runs", suffix: "runs", format: "integer" },
      { field: "week_start", prefix: "from " },
      { field: "week_end", prefix: "to " },
    ],
  },
] as const satisfies readonly MetricDisplaySpec[];
