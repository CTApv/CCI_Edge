import { useEffect, useMemo, useState } from "react";

const CHART_WIDTH = 960;
const DEFAULT_HEIGHT = 320;
const CHART_PADDING = { top: 24, right: 20, bottom: 58, left: 56 };
const CHART_PALETTE = ["#7cb8ff", "#5cd4bd", "#f2b35b", "#ff8f6b", "#83a8ff", "#8fe1ff"];

const timeFormatter = new Intl.DateTimeFormat("it-IT", {
  hour: "2-digit",
  minute: "2-digit",
});

const axisDateFormatter = new Intl.DateTimeFormat("it-IT", {
  day: "2-digit",
  month: "2-digit",
  year: "2-digit",
});

const rangeFormatter = new Intl.DateTimeFormat("it-IT", {
  day: "2-digit",
  month: "2-digit",
  year: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const valueFormatter = new Intl.NumberFormat("it-IT", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export const POWER_HISTORY_RANGE_PRESETS = [
  { id: "15m", label: "15 min", durationMs: 15 * 60 * 1000, maxPoints: 180 },
  { id: "1h", label: "1 h", durationMs: 60 * 60 * 1000, maxPoints: 240 },
  { id: "6h", label: "6 h", durationMs: 6 * 60 * 60 * 1000, maxPoints: 360 },
  { id: "1d", label: "24 h", durationMs: 24 * 60 * 60 * 1000, maxPoints: 480 },
  { id: "1w", label: "7 g", durationMs: 7 * 24 * 60 * 60 * 1000, maxPoints: 672 },
  { id: "1mo", label: "30 g", durationMs: 30 * 24 * 60 * 60 * 1000, maxPoints: 720 },
  { id: "3mo", label: "3 mesi", durationMs: 90 * 24 * 60 * 60 * 1000, maxPoints: 840 },
  { id: "1y", label: "1 anno", durationMs: 365 * 24 * 60 * 60 * 1000, maxPoints: 900 },
] as const;

export type PowerHistoryRangePresetId = (typeof POWER_HISTORY_RANGE_PRESETS)[number]["id"];

export const DEFAULT_POWER_HISTORY_RANGE_PRESET: PowerHistoryRangePresetId = "1d";

export type PowerHistoryChartSeries = {
  id: string;
  label: string;
  timestamps: string[];
  values: number[];
  emphasis?: boolean;
  color?: string;
};

type NormalizedSeries = PowerHistoryChartSeries & {
  color: string;
  alignedValues: Array<number | null>;
};

export type PowerHistoryVisibleSeries = {
  id: string;
  label: string;
  color: string;
  values: Array<number | null>;
  emphasis?: boolean;
};

export type PowerHistoryChartView = {
  labels: string[];
  visibleSeries: PowerHistoryVisibleSeries[];
  mode: "live" | "history";
  hiddenSeriesIds: string[];
};

type PowerHistoryChartProps = {
  labels: string[];
  series: PowerHistoryChartSeries[];
  emptyTitle: string;
  emptyMessage: string;
  loading?: boolean;
  errorMessage?: string | null;
  height?: number;
  onViewChange?: (view: PowerHistoryChartView) => void;
  rangePreset?: PowerHistoryRangePresetId;
  onRangePresetChange?: (presetId: PowerHistoryRangePresetId) => void;
  rangeStart?: string | null;
  rangeEnd?: string | null;
  rangeIsLive?: boolean;
  rangeMode?: "preset" | "custom";
  onRangeShift?: (direction: -1 | 1) => void;
  onRangeJumpToLive?: () => void;
  onRangeCustomApply?: (startIso: string, endIso: string) => void;
};

function padDatePart(value: number): string {
  return String(value).padStart(2, "0");
}

function formatDateTimeLocalInput(timestamp: string | null | undefined): string {
  if (!timestamp) {
    return "";
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return [
    date.getFullYear(),
    "-",
    padDatePart(date.getMonth() + 1),
    "-",
    padDatePart(date.getDate()),
    "T",
    padDatePart(date.getHours()),
    ":",
    padDatePart(date.getMinutes()),
  ].join("");
}

function parseDateTimeLocalInput(value: string): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toISOString();
}

function resolveLabels(labels: string[], series: PowerHistoryChartSeries[]): string[] {
  if (labels.length > 0) {
    return labels;
  }

  const timestamps = new Set<string>();
  for (const line of series) {
    for (const timestamp of line.timestamps) {
      timestamps.add(timestamp);
    }
  }

  return Array.from(timestamps).sort();
}

function parseTimestamp(timestamp: string): Date | null {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date;
}

function formatAxisDateLabel(timestamp: string): string {
  const date = parseTimestamp(timestamp);
  return date ? axisDateFormatter.format(date) : timestamp;
}

function formatAxisTimeLabel(timestamp: string): string {
  const date = parseTimestamp(timestamp);
  return date ? timeFormatter.format(date) : "";
}

function formatRangeLabel(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }

  return rangeFormatter.format(date);
}

function getAlignedValues(labels: string[], line: PowerHistoryChartSeries): Array<number | null> {
  const valuesByTimestamp = new Map<string, number>();
  const sampleCount = Math.min(line.timestamps.length, line.values.length);

  for (let index = 0; index < sampleCount; index += 1) {
    valuesByTimestamp.set(line.timestamps[index], line.values[index]);
  }

  return labels.map((label) => valuesByTimestamp.get(label) ?? null);
}

function getX(index: number, count: number): number {
  const innerWidth = CHART_WIDTH - CHART_PADDING.left - CHART_PADDING.right;
  if (count <= 1) {
    return CHART_PADDING.left + innerWidth / 2;
  }

  return CHART_PADDING.left + (innerWidth * index) / (count - 1);
}

function getY(value: number, domainMin: number, domainMax: number, chartHeight: number): number {
  const innerHeight = chartHeight - CHART_PADDING.top - CHART_PADDING.bottom;
  const domainSpan = Math.max(domainMax - domainMin, 1);
  return CHART_PADDING.top + innerHeight - ((value - domainMin) / domainSpan) * innerHeight;
}

function buildPath(
  values: Array<number | null>,
  domainMin: number,
  domainMax: number,
  chartHeight: number,
): string {
  let path = "";
  let segmentStarted = false;

  values.forEach((value, index) => {
    if (value === null) {
      segmentStarted = false;
      return;
    }

    const x = getX(index, values.length);
    const y = getY(value, domainMin, domainMax, chartHeight);
    path += `${segmentStarted ? " L" : "M"} ${x} ${y}`;
    segmentStarted = true;
  });

  return path.trim();
}

function normalizeSeries(labels: string[], series: PowerHistoryChartSeries[]): NormalizedSeries[] {
  return series.map((line, index) => ({
    ...line,
    color: line.color ?? CHART_PALETTE[index % CHART_PALETTE.length],
    alignedValues: getAlignedValues(labels, line),
  }));
}

function buildTicks(minValue: number, maxValue: number): number[] {
  const tickCount = 5;
  if (minValue === maxValue) {
    return [minValue];
  }

  return Array.from({ length: tickCount }, (_, index) => {
    const ratio = index / (tickCount - 1);
    return Number((maxValue - (maxValue - minValue) * ratio).toFixed(1));
  });
}

function buildXAxisTickIndexes(count: number, maxTickCount = 6): number[] {
  if (count <= 0) {
    return [];
  }
  if (count <= maxTickCount) {
    return Array.from({ length: count }, (_, index) => index);
  }

  const lastIndex = count - 1;
  const indexes = new Set<number>();
  for (let tickIndex = 0; tickIndex < maxTickCount; tickIndex += 1) {
    indexes.add(Math.round((lastIndex * tickIndex) / (maxTickCount - 1)));
  }

  return Array.from(indexes).sort((left, right) => left - right);
}

export function PowerHistoryChart({
  labels,
  series,
  emptyTitle,
  emptyMessage,
  loading = false,
  errorMessage = null,
  height = DEFAULT_HEIGHT,
  onViewChange,
  rangePreset = DEFAULT_POWER_HISTORY_RANGE_PRESET,
  onRangePresetChange,
  rangeStart = null,
  rangeEnd = null,
  rangeIsLive = true,
  rangeMode = "preset",
  onRangeShift,
  onRangeJumpToLive,
  onRangeCustomApply,
}: PowerHistoryChartProps) {
  const chartHeight = Math.max(height, 280);
  const domainLabels = useMemo(() => resolveLabels(labels, series), [labels, series]);
  const normalizedSeries = useMemo(() => normalizeSeries(domainLabels, series), [domainLabels, series]);
  const hasSamples = normalizedSeries.some(
    (line) => line.timestamps.length > 0 && line.values.length > 0,
  );
  const [hiddenSeriesIds, setHiddenSeriesIds] = useState<Set<string>>(new Set());
  const [customStartInput, setCustomStartInput] = useState(() =>
    formatDateTimeLocalInput(rangeStart),
  );
  const [customEndInput, setCustomEndInput] = useState(() => formatDateTimeLocalInput(rangeEnd));
  const [customRangeError, setCustomRangeError] = useState<string | null>(null);
  const showRangePresetControls = typeof onRangePresetChange === "function";
  const selectedRangePreset =
    POWER_HISTORY_RANGE_PRESETS.find((preset) => preset.id === rangePreset) ??
    POWER_HISTORY_RANGE_PRESETS.find((preset) => preset.id === DEFAULT_POWER_HISTORY_RANGE_PRESET)!;
  const canShiftBackward = typeof onRangeShift === "function";
  const canShiftForward =
    typeof onRangeShift === "function" &&
    !rangeIsLive &&
    rangeEnd !== null &&
    new Date(rangeEnd).getTime() < Date.now() - 30_000;
  const canJumpToLive = typeof onRangeJumpToLive === "function" && !rangeIsLive;
  const showRangeEditor =
    showRangePresetControls &&
    typeof onRangeCustomApply === "function" &&
    rangeStart !== null &&
    rangeEnd !== null;

  useEffect(() => {
    const nextIds = new Set(normalizedSeries.map((line) => line.id));
    setHiddenSeriesIds((current) => {
      const filtered = new Set(Array.from(current).filter((id) => nextIds.has(id)));
      return filtered.size === current.size ? current : filtered;
    });
  }, [normalizedSeries]);

  useEffect(() => {
    setCustomStartInput(formatDateTimeLocalInput(rangeStart));
    setCustomEndInput(formatDateTimeLocalInput(rangeEnd));
    setCustomRangeError(null);
  }, [rangeEnd, rangeStart]);

  const windowLabels = domainLabels;

  const visibleSeries = useMemo(
    () =>
      normalizedSeries
        .filter((line) => !hiddenSeriesIds.has(line.id))
        .map((line) => ({
          ...line,
          alignedValues: line.alignedValues,
        })),
    [hiddenSeriesIds, normalizedSeries],
  );

  useEffect(() => {
    if (!onViewChange) {
      return;
    }

    onViewChange({
      labels: windowLabels,
      visibleSeries: visibleSeries.map((line) => ({
        id: line.id,
        label: line.label,
        color: line.color,
        values: line.alignedValues,
        emphasis: line.emphasis,
      })),
      mode: "history",
      hiddenSeriesIds: Array.from(hiddenSeriesIds),
    });
  }, [hiddenSeriesIds, onViewChange, visibleSeries, windowLabels]);

  let domainMax = 1;
  let domainMin = 0;
  let visiblePointCount = 0;
  for (const line of visibleSeries) {
    for (const value of line.alignedValues) {
      if (value === null) {
        continue;
      }
      visiblePointCount += 1;
      domainMax = Math.max(domainMax, value);
      domainMin = Math.min(domainMin, value);
    }
  }
  const yTicks = buildTicks(domainMin, domainMax);
  const zeroLineY =
    domainMin < 0 && domainMax > 0 ? getY(0, domainMin, domainMax, chartHeight) : null;
  const lastIndex = windowLabels.length - 1;
  const xAxisTickIndexes = buildXAxisTickIndexes(windowLabels.length);
  const firstWindowLabel = windowLabels[0] ?? null;
  const lastWindowLabel = windowLabels[windowLabels.length - 1] ?? null;
  const viewAnimationKey = `${rangePreset}-${firstWindowLabel ?? "empty"}-${lastWindowLabel ?? "empty"}-${
    hiddenSeriesIds.size
  }`;
  const pointStride = Math.max(1, Math.ceil(visiblePointCount / 900));
  const densePointMode = pointStride > 1;

  function toggleSeries(seriesId: string): void {
    setHiddenSeriesIds((current) => {
      const next = new Set(current);
      if (next.has(seriesId)) {
        next.delete(seriesId);
      } else {
        next.add(seriesId);
      }
      return next;
    });
  }

  function showAllSeries(): void {
    setHiddenSeriesIds(new Set());
  }

  function selectRangePreset(presetId: PowerHistoryRangePresetId): void {
    onRangePresetChange?.(presetId);
  }

  function applyCustomRange(): void {
    const startIso = parseDateTimeLocalInput(customStartInput);
    const endIso = parseDateTimeLocalInput(customEndInput);
    const startMs = startIso ? new Date(startIso).getTime() : Number.NaN;
    const endMs = endIso ? new Date(endIso).getTime() : Number.NaN;

    if (!startIso || !endIso || !Number.isFinite(startMs) || !Number.isFinite(endMs)) {
      setCustomRangeError("Seleziona data e ora di inizio e fine.");
      return;
    }

    if (startMs >= endMs) {
      setCustomRangeError("La data di inizio deve precedere la data di fine.");
      return;
    }

    if (endMs > Date.now() + 60_000) {
      setCustomRangeError("La data di fine non puo essere nel futuro.");
      return;
    }

    setCustomRangeError(null);
    onRangeCustomApply?.(startIso, endIso);
  }

  const emptyStateTitle = loading && !hasSamples
    ? "Sincronizzazione campioni in corso"
    : errorMessage && !hasSamples
      ? "Impossibile visualizzare lo storico"
      : emptyTitle;
  const emptyStateMessage = loading && !hasSamples
    ? "Il frontend sta caricando lo storico reale dal backend."
    : errorMessage && !hasSamples
      ? errorMessage
      : emptyMessage;
  const emptyStateClassName = `history-chart-empty ${
    errorMessage && !hasSamples ? "history-chart-empty--error" : ""
  }`;

  return (
    <div className="history-chart-shell">
      <div className="history-chart-toolbar">
        <div className="history-chart-toolbar-copy">
          <strong>
            {showRangePresetControls
              ? rangeMode === "custom"
                ? "Periodo manuale"
                : `Periodo ${selectedRangePreset.label}`
              : "Periodo selezionato"}
          </strong>
          <p>
            {firstWindowLabel && lastWindowLabel
              ? `${formatRangeLabel(firstWindowLabel)} - ${formatRangeLabel(lastWindowLabel)}`
              : "Nessun intervallo disponibile"}
          </p>
        </div>
        <div className="history-chart-toolbar-actions">
          <span className="history-chart-sample-pill">{domainLabels.length} campioni</span>
          {hiddenSeriesIds.size > 0 ? (
            <button className="history-chart-mode-button" type="button" onClick={showAllSeries}>
              Mostra tutto
            </button>
          ) : null}
        </div>
      </div>

      {showRangePresetControls ? (
        <div className="history-chart-control-stack">
          <div className="history-chart-control-row">
            <div className="history-chart-presets" aria-label="Filtro periodo storico">
              {POWER_HISTORY_RANGE_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  className={`history-chart-preset-button ${
                    preset.id === selectedRangePreset.id && rangeMode === "preset"
                      ? "history-chart-preset-button--active"
                      : ""
                  }`}
                  type="button"
                  onClick={() => selectRangePreset(preset.id)}
                  title={`Mostra ultimi ${preset.label}`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            <div className="history-chart-time-nav" aria-label="Navigazione temporale">
              <button
                className="history-chart-nav-button"
                type="button"
                onClick={() => onRangeShift?.(-1)}
                disabled={!canShiftBackward}
              >
                Indietro
              </button>
              <button
                className="history-chart-nav-button"
                type="button"
                onClick={() => onRangeShift?.(1)}
                disabled={!canShiftForward}
              >
                Avanti
              </button>
              <button
                className="history-chart-nav-button history-chart-nav-button--live"
                type="button"
                onClick={onRangeJumpToLive}
                disabled={!canJumpToLive}
              >
                Adesso
              </button>
            </div>
          </div>
          {showRangeEditor ? (
            <div className="history-chart-range-editor">
              <label>
                <span>Da</span>
                <input
                  type="datetime-local"
                  value={customStartInput}
                  onChange={(event) => setCustomStartInput(event.currentTarget.value)}
                />
              </label>
              <label>
                <span>A</span>
                <input
                  type="datetime-local"
                  value={customEndInput}
                  onChange={(event) => setCustomEndInput(event.currentTarget.value)}
                />
              </label>
              <button className="history-chart-apply-button" type="button" onClick={applyCustomRange}>
                Applica periodo
              </button>
              {customRangeError ? (
                <span className="history-chart-range-error">{customRangeError}</span>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {hasSamples ? (
      <div className="history-chart-surface" style={{ minHeight: `${chartHeight}px` }}>
        <svg
          key={viewAnimationKey}
          className={`history-chart-svg ${densePointMode ? "history-chart-svg--dense" : ""}`}
          viewBox={`0 0 ${CHART_WIDTH} ${chartHeight}`}
          role="img"
          aria-label="Storico di potenza attiva"
        >
          {yTicks.map((tickValue) => {
            const y = getY(tickValue, domainMin, domainMax, chartHeight);
            return (
              <g key={tickValue}>
                <line
                  className="history-chart-grid-line"
                  x1={CHART_PADDING.left}
                  y1={y}
                  x2={CHART_WIDTH - CHART_PADDING.right}
                  y2={y}
                />
                <text className="history-chart-axis-label" x="0" y={y + 4}>
                  {valueFormatter.format(tickValue)}
                </text>
              </g>
            );
          })}

          {zeroLineY !== null ? (
            <line
              className="history-chart-zero-line"
              x1={CHART_PADDING.left}
              y1={zeroLineY}
              x2={CHART_WIDTH - CHART_PADDING.right}
              y2={zeroLineY}
            />
          ) : null}

          {xAxisTickIndexes.map((index) => {
            const label = windowLabels[index];
            if (!label) {
              return null;
            }
            return (
              <text
                key={label}
                className="history-chart-axis-label history-chart-axis-label--x"
                x={getX(index, windowLabels.length)}
                y={chartHeight - 26}
                textAnchor={index === 0 ? "start" : index === lastIndex ? "end" : "middle"}
              >
                <title>{formatRangeLabel(label)}</title>
                <tspan className="history-chart-axis-date" x={getX(index, windowLabels.length)}>
                  {formatAxisDateLabel(label)}
                </tspan>
                <tspan
                  className="history-chart-axis-time"
                  x={getX(index, windowLabels.length)}
                  dy="15"
                >
                  {formatAxisTimeLabel(label)}
                </tspan>
              </text>
            );
          })}

          {visibleSeries.map((line) => (
            <path
              key={`${line.id}-${viewAnimationKey}`}
              className={`history-chart-line ${line.emphasis ? "history-chart-line--emphasis" : ""}`}
              d={buildPath(line.alignedValues, domainMin, domainMax, chartHeight)}
              pathLength={1}
              stroke={line.color}
            />
          ))}

          {visibleSeries.map((line) =>
            line.alignedValues.map((value, index) => {
              if (value === null) {
                return null;
              }
              if (index !== 0 && index !== lastIndex && index % pointStride !== 0) {
                return null;
              }

              return (
                <circle
                  key={`${line.id}-${windowLabels[index]}-${viewAnimationKey}`}
                  className={`history-chart-point ${line.emphasis ? "history-chart-point--emphasis" : ""}`}
                  cx={getX(index, windowLabels.length)}
                  cy={getY(value, domainMin, domainMax, chartHeight)}
                  r={line.emphasis ? 3.4 : 2.4}
                  fill={line.color}
                />
              );
            }),
          )}
        </svg>

        {visibleSeries.length === 0 ? (
          <div className="history-chart-overlay-note">
            Hai nascosto tutte le serie. Riattivane almeno una dalla legenda.
          </div>
        ) : null}
      </div>
      ) : (
        <div className={emptyStateClassName}>
          <p className="panel-kicker">Storico potenza</p>
          <h3>{emptyStateTitle}</h3>
          <p className="history-chart-empty-copy">{emptyStateMessage}</p>
        </div>
      )}

      {hasSamples ? (
      <div className="history-chart-legend">
        {normalizedSeries.map((line) => {
          const hidden = hiddenSeriesIds.has(line.id);
          return (
            <button
              key={line.id}
              type="button"
              className={`history-chart-legend-item ${
                line.emphasis ? "history-chart-legend-item--emphasis" : ""
              } ${hidden ? "history-chart-legend-item--hidden" : ""}`}
              onClick={() => toggleSeries(line.id)}
            >
              <span
                className="history-chart-legend-swatch"
                style={{ backgroundColor: line.color }}
              />
              {line.label}
            </button>
          );
        })}
      </div>
      ) : null}

      {errorMessage && hasSamples ? (
        <p className="history-chart-note">
          Ultimo aggiornamento storico non disponibile. {errorMessage}
        </p>
      ) : null}
    </div>
  );
}
