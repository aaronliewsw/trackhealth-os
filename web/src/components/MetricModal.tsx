import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { fetchReadings, fetchSeries } from "../data/api";
import type { MetricDisplaySpec, NumberFormat } from "../data/metricRegistry";
import type {
  MetricKey,
  MetricReading,
  ReadingsResponse,
  SeriesPoint,
  SeriesResponse,
  StateMetric,
} from "../types";

const RANGE_OPTIONS = ["1d", "7d", "4w", "1y"] as const;

type RangeKey = (typeof RANGE_OPTIONS)[number];
type ChartTone = "accent" | "positive";

interface MetricModalProps {
  metric: StateMetric;
  spec: MetricDisplaySpec;
  dashboardDate: string;
  onClose: () => void;
}

interface ChartDatum {
  at: string;
  label: string;
  value: number;
}

interface ChartDomain {
  min: number;
  max: number;
}

interface DisplayedSeries {
  range: RangeKey;
  response: SeriesResponse;
}

const chartFrame = {
  width: 680,
  height: 264,
  top: 20,
  right: 20,
  bottom: 36,
  left: 56,
};

const numberFormatter = new Intl.NumberFormat("en-US");
const decimalFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
  minimumFractionDigits: 1,
});
const compactFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
  notation: "compact",
});

const detailTitles: Record<MetricKey, string> = {
  sleep: "Sleep trend",
  hrv: "Nightly HRV",
  resting_hr: "Resting baseline",
  steps: "Step volume",
  stress: "Intraday stress",
  body_battery: "Intraday body battery",
  vo2_max: "Cardio estimate",
  fitness_age: "Fitness age",
  training_readiness: "Readiness factors",
  running: "Running distance",
};

const sparseSeriesMessage = "Not enough history yet — still syncing";

function readField(value: object, field: string): unknown {
  return (value as Record<string, unknown>)[field];
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatNumber(value: number, format?: NumberFormat): string {
  return format === "decimal1" ? decimalFormatter.format(value) : numberFormatter.format(Math.round(value));
}

function formatAxisValue(value: number, format?: NumberFormat): string {
  if (Math.abs(value) >= 10000) {
    return compactFormatter.format(value);
  }

  if (format === "decimal1" || Math.abs(value) < 10) {
    return decimalFormatter.format(value);
  }

  return numberFormatter.format(Math.round(value));
}

function formatPrimitive(value: unknown, format?: NumberFormat): string | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  if (typeof value === "number") {
    return formatNumber(value, format);
  }

  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }

  return String(value);
}

function timestampFor(value: string): number {
  return new Date(value.includes("T") ? value : `${value}T00:00:00`).getTime();
}

function sortByTimestamp<T extends { at: string }>(items: T[]): T[] {
  return items
    .map((item, index) => ({ index, item, timestamp: timestampFor(item.at) }))
    .sort((left, right) => {
      const leftIsValid = Number.isFinite(left.timestamp);
      const rightIsValid = Number.isFinite(right.timestamp);

      if (leftIsValid && rightIsValid && left.timestamp !== right.timestamp) {
        return left.timestamp - right.timestamp;
      }

      return left.index - right.index;
    })
    .map(({ item }) => item);
}

function formatDateLabel(value: string): string {
  const date = new Date(value.includes("T") ? value : `${value}T00:00:00`);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "short",
  }).format(date);
}

function formatTimeLabel(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function toTitleCase(value: string): string {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(" ");
}

function toSeriesData(points: SeriesPoint[]): ChartDatum[] {
  return sortByTimestamp(points)
    .filter((point) => Number.isFinite(point.value))
    .map((point) => ({
      at: point.at,
      label: formatDateLabel(point.at),
      value: point.value,
    }));
}

function toReadingData(readings: MetricReading[]): ChartDatum[] {
  return sortByTimestamp(readings)
    .filter((reading) => Number.isFinite(reading.value))
    .map((reading) => ({
      at: reading.at,
      label: formatTimeLabel(reading.at),
      value: reading.value,
    }));
}

function isColumnMetric(key: MetricKey): boolean {
  return key === "steps" || key === "running";
}

function metricUnit(metric: StateMetric, spec: MetricDisplaySpec): string | null {
  return metric.unit ?? spec.unit;
}

function getDomain(values: number[], includeZero: boolean): ChartDomain {
  if (values.length === 0) {
    return { min: 0, max: 1 };
  }

  let min = Math.min(...values);
  let max = Math.max(...values);

  if (includeZero) {
    min = Math.min(0, min);
    max = Math.max(0, max);
  }

  if (min === max) {
    const padding = Math.max(Math.abs(max) * 0.12, 1);
    return { min: min - padding, max: max + padding };
  }

  const padding = (max - min) * 0.12;

  return {
    min: includeZero ? min : min - padding,
    max: max + padding,
  };
}

function yFor(value: number, domain: ChartDomain): number {
  const plotHeight = chartFrame.height - chartFrame.top - chartFrame.bottom;
  const domainSpan = domain.max - domain.min;

  if (!Number.isFinite(value) || !Number.isFinite(domainSpan) || domainSpan <= 0) {
    return chartFrame.top + plotHeight / 2;
  }

  return (
    chartFrame.height -
    chartFrame.bottom -
    ((value - domain.min) / domainSpan) * plotHeight
  );
}

function xFor(index: number, length: number): number {
  const plotWidth = chartFrame.width - chartFrame.left - chartFrame.right;

  if (!Number.isFinite(index) || length <= 1) {
    return chartFrame.left + plotWidth / 2;
  }

  const safeIndex = Math.min(Math.max(index, 0), length - 1);
  return chartFrame.left + (plotWidth * safeIndex) / (length - 1);
}

function gridTicks(domain: ChartDomain): number[] {
  return [domain.min, domain.min + (domain.max - domain.min) / 2, domain.max];
}

function linePath(data: ChartDatum[], domain: ChartDomain): string {
  if (data.length < 2) {
    return "";
  }

  return data
    .map((datum, index) => {
      const command = index === 0 ? "M" : "L";
      return `${command} ${xFor(index, data.length)} ${yFor(datum.value, domain)}`;
    })
    .join(" ");
}

function areaPath(data: ChartDatum[], domain: ChartDomain): string {
  if (data.length < 2) {
    return "";
  }

  const baseY = chartFrame.height - chartFrame.bottom;
  const lastX = xFor(data.length - 1, data.length);
  const firstX = xFor(0, data.length);

  return `${linePath(data, domain)} L ${lastX} ${baseY} L ${firstX} ${baseY} Z`;
}

function lastDatum(data: ChartDatum[]): ChartDatum | null {
  return data.length > 0 ? data[data.length - 1] : null;
}

function renderGrid(domain: ChartDomain, format?: NumberFormat) {
  return gridTicks(domain).map((tick) => {
    const y = yFor(tick, domain);

    return (
      <g key={tick}>
        <line
          className="metric-chart__gridline"
          x1={chartFrame.left}
          x2={chartFrame.width - chartFrame.right}
          y1={y}
          y2={y}
        />
        <text className="metric-chart__axis-label" x={chartFrame.left - 8} y={y + 4} textAnchor="end">
          {formatAxisValue(tick, format)}
        </text>
      </g>
    );
  });
}

function renderXAxisLabels(data: ChartDatum[]) {
  if (data.length === 0) {
    return null;
  }

  const first = data[0];
  const last = data[data.length - 1];
  const y = chartFrame.height - 8;

  if (first.label === last.label) {
    return (
      <text className="metric-chart__axis-label" x={chartFrame.left} y={y}>
        {first.label}
      </text>
    );
  }

  return (
    <>
      <text className="metric-chart__axis-label" x={chartFrame.left} y={y}>
        {first.label}
      </text>
      <text
        className="metric-chart__axis-label"
        x={chartFrame.width - chartFrame.right}
        y={y}
        textAnchor="end"
      >
        {last.label}
      </text>
    </>
  );
}

function LineSvgChart({
  data,
  valueFormat,
  unit,
  ariaLabel,
  tone = "accent",
  area = false,
  baseline,
  indicator,
}: {
  data: ChartDatum[];
  valueFormat?: NumberFormat;
  unit?: string | null;
  ariaLabel: string;
  tone?: ChartTone;
  area?: boolean;
  baseline?: { low: number; high: number };
  indicator?: { value: number; label: string };
}) {
  if (data.length === 0) {
    return <div className="metric-modal__empty">No chart points returned.</div>;
  }

  const domainValues = data.map((datum) => datum.value);

  if (baseline) {
    domainValues.push(baseline.low, baseline.high);
  }

  if (indicator) {
    domainValues.push(indicator.value);
  }

  const domain = getDomain(domainValues, false);
  const latest = lastDatum(data);
  const latestX = latest ? xFor(data.length - 1, data.length) : chartFrame.left;
  const latestY = latest ? yFor(latest.value, domain) : chartFrame.top;
  const labelX = latestX > chartFrame.width - chartFrame.right - 96 ? latestX - 8 : latestX + 8;
  const labelAnchor = latestX > chartFrame.width - chartFrame.right - 96 ? "end" : "start";
  const lineClassName =
    tone === "positive" ? "metric-chart__line metric-chart__line--positive" : "metric-chart__line";
  const trendPath = linePath(data, domain);
  const filledAreaPath = areaPath(data, domain);

  return (
    <svg className={`metric-chart metric-chart--${tone}`} role="img" aria-label={ariaLabel} viewBox="0 0 680 264">
      {renderGrid(domain, valueFormat)}
      {baseline ? (
        <rect
          className="metric-chart__band"
          x={chartFrame.left}
          y={Math.min(yFor(baseline.high, domain), yFor(baseline.low, domain))}
          width={chartFrame.width - chartFrame.left - chartFrame.right}
          height={Math.abs(yFor(baseline.low, domain) - yFor(baseline.high, domain))}
        />
      ) : null}
      {area && filledAreaPath ? <path className="metric-chart__area" d={filledAreaPath} /> : null}
      {trendPath ? <path className={lineClassName} d={trendPath} /> : null}
      {indicator ? (
        <>
          <line
            className="metric-chart__indicator"
            x1={chartFrame.left}
            x2={chartFrame.width - chartFrame.right}
            y1={yFor(indicator.value, domain)}
            y2={yFor(indicator.value, domain)}
          />
          <text
            className="metric-chart__value-label metric-chart__value-label--positive"
            x={chartFrame.width - chartFrame.right}
            y={yFor(indicator.value, domain) - 8}
            textAnchor="end"
          >
            {indicator.label}
          </text>
        </>
      ) : null}
      {latest ? (
        <>
          <circle className="metric-chart__point" cx={latestX} cy={latestY} r="4" />
          <text className="metric-chart__value-label" x={labelX} y={latestY - 8} textAnchor={labelAnchor}>
            {formatNumber(latest.value, valueFormat)}
            {unit ? ` ${unit}` : ""}
          </text>
        </>
      ) : null}
      {renderXAxisLabels(data)}
    </svg>
  );
}

function ColumnSvgChart({
  data,
  valueFormat,
  unit,
  ariaLabel,
}: {
  data: ChartDatum[];
  valueFormat?: NumberFormat;
  unit?: string | null;
  ariaLabel: string;
}) {
  if (data.length === 0) {
    return <div className="metric-modal__empty">No chart points returned.</div>;
  }

  const domain = getDomain(
    data.map((datum) => datum.value),
    true,
  );
  const plotWidth = chartFrame.width - chartFrame.left - chartFrame.right;
  const slotWidth = plotWidth / data.length;
  const barWidth = Math.max(8, slotWidth * 0.56);
  const zeroY = yFor(0, domain);
  const maxPoint = data.reduce((highest, datum) => (datum.value > highest.value ? datum : highest), data[0]);
  const maxIndex = data.findIndex((datum) => datum === maxPoint);
  const maxX = chartFrame.left + slotWidth * maxIndex + slotWidth / 2;
  const maxY = yFor(maxPoint.value, domain);

  return (
    <svg className="metric-chart" role="img" aria-label={ariaLabel} viewBox="0 0 680 264">
      {renderGrid(domain, valueFormat)}
      <line
        className="metric-chart__axis-line"
        x1={chartFrame.left}
        x2={chartFrame.width - chartFrame.right}
        y1={zeroY}
        y2={zeroY}
      />
      {data.map((datum, index) => {
        const centerX = chartFrame.left + slotWidth * index + slotWidth / 2;
        const valueY = yFor(datum.value, domain);
        const y = Math.min(valueY, zeroY);
        const height = Math.max(1, Math.abs(zeroY - valueY));

        return (
          <rect
            className="metric-chart__bar"
            key={`${datum.at}-${index}`}
            x={centerX - barWidth / 2}
            y={y}
            width={barWidth}
            height={height}
          />
        );
      })}
      <text className="metric-chart__value-label" x={maxX} y={maxY - 8} textAnchor="middle">
        {formatNumber(maxPoint.value, valueFormat)}
        {unit ? ` ${unit}` : ""}
      </text>
      {renderXAxisLabels(data)}
    </svg>
  );
}

function ChartFrame({
  children,
  isBusy = false,
  statusMessage,
}: {
  children: ReactNode;
  isBusy?: boolean;
  statusMessage?: string | null;
}) {
  return (
    <div className={`metric-modal__chart-frame${isBusy ? " metric-modal__chart-frame--busy" : ""}`}>
      <div className="metric-modal__chart-visual">{children}</div>
      {statusMessage ? (
        <p className="metric-modal__chart-status" role="status">
          {statusMessage}
        </p>
      ) : null}
    </div>
  );
}

function MetricTrendChart({
  series,
  metric,
  spec,
  range,
  isBusy = false,
  statusMessage,
}: {
  series: SeriesResponse;
  metric: StateMetric;
  spec: MetricDisplaySpec;
  range: RangeKey;
  isBusy?: boolean;
  statusMessage?: string | null;
}) {
  const data = toSeriesData(series.points);
  const unit = metricUnit(metric, spec);
  const useColumns = isColumnMetric(spec.key);
  const hasEnoughHistory = data.length >= 2;
  const rangeTotal = data.reduce((total, datum) => total + datum.value, 0);
  const latest = lastDatum(data);
  const summary = !hasEnoughHistory
    ? "--"
    : useColumns
    ? `${formatNumber(rangeTotal, spec.valueFormat)}${unit ? ` ${unit}` : ""}`
    : latest
      ? `${formatNumber(latest.value, spec.valueFormat)}${unit ? ` ${unit}` : ""}`
      : "--";

  return (
    <section
      aria-busy={isBusy || undefined}
      aria-label={`${spec.label} ${range} range`}
      className="metric-modal__chart-block"
    >
      <div className="metric-modal__chart-head">
        <div>
          <p className="metric-modal__mini-label">{useColumns ? "Range total" : "Range trend"}</p>
          <strong>{summary}</strong>
        </div>
        <span className="metric-modal__range-pill">{range}</span>
      </div>
      <ChartFrame isBusy={isBusy} statusMessage={statusMessage}>
        {!hasEnoughHistory ? (
          <div className="metric-modal__empty metric-modal__empty--chart">{sparseSeriesMessage}</div>
        ) : useColumns ? (
          <ColumnSvgChart
            ariaLabel={`${spec.label} ${range} column chart`}
            data={data}
            unit={unit}
            valueFormat={spec.valueFormat}
          />
        ) : (
          <LineSvgChart
            ariaLabel={`${spec.label} ${range} trend line chart`}
            data={data}
            unit={unit}
            valueFormat={spec.valueFormat}
          />
        )}
      </ChartFrame>
    </section>
  );
}

function MetricTrendPlaceholder({
  isBusy,
  message,
  range,
  spec,
}: {
  isBusy: boolean;
  message: string;
  range: RangeKey;
  spec: MetricDisplaySpec;
}) {
  const useColumns = isColumnMetric(spec.key);

  return (
    <section
      aria-busy={isBusy || undefined}
      aria-label={`${spec.label} ${range} range`}
      className="metric-modal__chart-block"
    >
      <div className="metric-modal__chart-head">
        <div>
          <p className="metric-modal__mini-label">{useColumns ? "Range total" : "Range trend"}</p>
          <strong>--</strong>
        </div>
        <span className="metric-modal__range-pill">{range}</span>
      </div>
      <ChartFrame>
        <div className="metric-modal__empty metric-modal__empty--chart" role={isBusy ? "status" : "alert"}>
          {message}
        </div>
      </ChartFrame>
    </section>
  );
}

function factorNumber(factors: ReadingsResponse["factors"] | undefined, key: string): number | null {
  return asNumber(factors?.[key]);
}

function HrvReadingChart({
  metric,
  spec,
  readings,
}: {
  metric: StateMetric;
  spec: MetricDisplaySpec;
  readings: ReadingsResponse;
}) {
  const data = toReadingData(readings.readings);
  const baselineLow = factorNumber(readings.factors, "baseline_low") ?? asNumber(readField(metric.value, "baseline_low"));
  const baselineHigh =
    factorNumber(readings.factors, "baseline_high") ?? asNumber(readField(metric.value, "baseline_high"));
  const weeklyAvg = asNumber(readField(metric.value, "weekly_avg"));
  const baseline =
    baselineLow !== null && baselineHigh !== null ? { low: baselineLow, high: baselineHigh } : undefined;
  const indicator =
    weeklyAvg !== null ? { value: weeklyAvg, label: `weekly avg ${formatNumber(weeklyAvg, spec.valueFormat)}` } : undefined;

  return (
    <LineSvgChart
      ariaLabel="HRV nightly readings with baseline band"
      baseline={baseline}
      data={data}
      indicator={indicator}
      tone="positive"
      unit={metricUnit(metric, spec)}
      valueFormat={spec.valueFormat}
    />
  );
}

function ReadingDetailChart({
  metric,
  spec,
  readings,
}: {
  metric: StateMetric;
  spec: MetricDisplaySpec;
  readings: ReadingsResponse;
}) {
  const data = toReadingData(readings.readings);

  if (spec.key === "hrv") {
    return <HrvReadingChart metric={metric} readings={readings} spec={spec} />;
  }

  if (spec.key === "steps") {
    return (
      <ColumnSvgChart
        ariaLabel="Steps intraday readings column chart"
        data={data}
        unit={metricUnit(metric, spec)}
        valueFormat={spec.valueFormat}
      />
    );
  }

  return (
    <LineSvgChart
      area={spec.key === "stress" || spec.key === "body_battery"}
      ariaLabel={`${spec.label} intraday readings line chart`}
      data={data}
      tone="positive"
      unit={metricUnit(metric, spec)}
      valueFormat={spec.valueFormat}
    />
  );
}

function ContractValueSummary({ metric, spec }: { metric: StateMetric; spec: MetricDisplaySpec }) {
  const items = spec.secondary
    .map((item) => {
      const raw = readField(metric.value, item.field);
      const formatted = formatPrimitive(raw, item.format);

      if (!formatted) {
        return null;
      }

      return {
        label: item.prefix ? item.prefix.trim() : toTitleCase(String(item.field)),
        value: `${formatted}${item.unit ? ` ${item.unit}` : ""}${item.suffix ? ` ${item.suffix}` : ""}`,
      };
    })
    .filter((item): item is { label: string; value: string } => item !== null);

  if (items.length === 0) {
    return null;
  }

  return (
    <dl className="metric-modal__summary-grid">
      {items.map((item) => (
        <div key={`${item.label}-${item.value}`}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function FactorList({ factors }: { factors: ReadingsResponse["factors"] }) {
  if (!factors) {
    return null;
  }

  const entries = Object.entries(factors);

  if (entries.length === 0) {
    return null;
  }

  return (
    <dl className="metric-modal__factor-list">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{toTitleCase(key)}</dt>
          <dd>{formatPrimitive(value) ?? "--"}</dd>
        </div>
      ))}
    </dl>
  );
}

function MetricDetailPanel({
  metric,
  spec,
  readings,
  readingsError,
  readingsLoading,
}: {
  metric: StateMetric;
  spec: MetricDisplaySpec;
  readings: ReadingsResponse | null;
  readingsError: string | null;
  readingsLoading: boolean;
}) {
  const hasFineGrainedReadings = metric.has_readings || spec.hasReadings;

  return (
    <section className="metric-modal__detail-panel" aria-label={`${spec.label} detail`}>
      <div className="metric-modal__detail-head">
        <p className="metric-modal__mini-label">Detail</p>
        <strong>{detailTitles[spec.key]}</strong>
      </div>

      {hasFineGrainedReadings ? (
        <div className="metric-modal__reading-block">
          {readingsLoading ? <div className="metric-modal__empty">Loading readings.</div> : null}
          {readingsError ? <div className="metric-modal__empty">{readingsError}</div> : null}
          {!readingsLoading && !readingsError && readings ? (
            <ReadingDetailChart metric={metric} readings={readings} spec={spec} />
          ) : null}
        </div>
      ) : null}

      {spec.key === "training_readiness" ? (
        <div className="metric-modal__reading-block">
          {readingsLoading ? <div className="metric-modal__empty">Loading factors.</div> : null}
          {readingsError ? <div className="metric-modal__empty">{readingsError}</div> : null}
        </div>
      ) : null}

      <ContractValueSummary metric={metric} spec={spec} />
      <FactorList factors={readings?.factors ?? null} />
    </section>
  );
}

export function MetricModal({ metric, spec, dashboardDate, onClose }: MetricModalProps) {
  const [range, setRange] = useState<RangeKey>("7d");
  const [displayedSeries, setDisplayedSeries] = useState<DisplayedSeries | null>(null);
  const [seriesLoading, setSeriesLoading] = useState(true);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [readings, setReadings] = useState<ReadingsResponse | null>(null);
  const [readingsLoading, setReadingsLoading] = useState(false);
  const [readingsError, setReadingsError] = useState<string | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const label = metric.label || spec.label;
  const primaryValue = formatPrimitive(readField(metric.value, spec.trendField), spec.valueFormat) ?? "--";
  const shouldFetchReadings = metric.has_readings || spec.hasReadings || spec.key === "training_readiness";

  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    let stale = false;

    setSeriesLoading(true);
    setSeriesError(null);

    fetchSeries(spec.key, range)
      .then((nextSeries) => {
        if (stale) {
          return;
        }

        setDisplayedSeries({ range, response: nextSeries });
      })
      .catch((error: unknown) => {
        if (stale) {
          return;
        }

        setSeriesError(error instanceof Error ? error.message : "Unable to load series.");
      })
      .finally(() => {
        if (!stale) {
          setSeriesLoading(false);
        }
      });

    return () => {
      stale = true;
    };
  }, [range, spec.key]);

  useEffect(() => {
    let stale = false;

    if (!shouldFetchReadings) {
      setReadings(null);
      setReadingsError(null);
      setReadingsLoading(false);
      return () => {
        stale = true;
      };
    }

    setReadingsLoading(true);
    setReadingsError(null);

    fetchReadings(spec.key, dashboardDate)
      .then((nextReadings) => {
        if (stale) {
          return;
        }

        setReadings(nextReadings);
      })
      .catch((error: unknown) => {
        if (stale) {
          return;
        }

        setReadings(null);
        setReadingsError(error instanceof Error ? error.message : "Unable to load readings.");
      })
      .finally(() => {
        if (!stale) {
          setReadingsLoading(false);
        }
      });

    return () => {
      stale = true;
    };
  }, [dashboardDate, shouldFetchReadings, spec.key]);

  const headlineMeta = useMemo(() => {
    const unit = metricUnit(metric, spec);
    return `${primaryValue}${unit ? ` ${unit}` : ""}`;
  }, [metric, primaryValue, spec]);
  const chartStatusMessage =
    displayedSeries && seriesLoading
      ? `Loading ${range}.`
      : displayedSeries && seriesError
        ? seriesError
        : null;
  const placeholderMessage = seriesError ?? "Loading range.";

  return (
    <div
      className="metric-modal__scrim"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section
        aria-label={label}
        aria-modal="true"
        className="metric-modal"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header className="metric-modal__header">
          <div>
            <p className="metric-modal__section">{spec.section}</p>
            <h2>{label}</h2>
            <p className="metric-modal__headline-meta">{headlineMeta}</p>
          </div>
          <button
            aria-label="Close"
            className="metric-modal__close"
            onClick={onClose}
            ref={closeButtonRef}
            type="button"
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>

        <div className="metric-modal__range-tabs" role="tablist" aria-label={`${label} range`}>
          {RANGE_OPTIONS.map((option) => (
            <button
              aria-selected={range === option}
              className="metric-modal__range-tab"
              key={option}
              onClick={(event) => {
                event.stopPropagation();
                setRange(option);
              }}
              onMouseDown={(event) => event.stopPropagation()}
              role="tab"
              type="button"
            >
              {option}
            </button>
          ))}
        </div>

        {displayedSeries ? (
          <MetricTrendChart
            isBusy={seriesLoading}
            metric={metric}
            range={displayedSeries.range}
            series={displayedSeries.response}
            spec={spec}
            statusMessage={chartStatusMessage}
          />
        ) : (
          <MetricTrendPlaceholder
            isBusy={seriesLoading}
            message={placeholderMessage}
            range={range}
            spec={spec}
          />
        )}

        <MetricDetailPanel
          metric={metric}
          readings={readings}
          readingsError={readingsError}
          readingsLoading={readingsLoading}
          spec={spec}
        />
      </section>
    </div>
  );
}
