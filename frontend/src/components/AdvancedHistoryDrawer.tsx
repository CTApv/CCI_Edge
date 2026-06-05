import { useEffect, useMemo, useState } from "react";

import {
  getDashboardPowerHistory,
  getDevicePowerHistory,
  type Device,
  type DevicePowerHistoryResponse,
  type FleetPowerHistoryResponse,
  type PowerHistoryQuery,
} from "../api";
import {
  PowerHistoryChart,
  type PowerHistoryChartSeries,
  type PowerHistoryChartView,
} from "./PowerHistoryChart";
import { getSettingsAccentClass, SETTINGS_SECTION_CONTENT } from "../settingsSections";

type AdvancedHistoryDrawerProps = {
  open: boolean;
  scope: "fleet" | "device";
  device?: Device | null;
  onClose: () => void;
};

type HistoryPreset = "24h" | "7d" | "30d" | "custom";

const QUERY_MAX_POINTS = 720;

const dateTimeFormatter = new Intl.DateTimeFormat("it-IT", {
  dateStyle: "medium",
  timeStyle: "short",
});

function buildFleetHistorySeries(history: FleetPowerHistoryResponse | null): PowerHistoryChartSeries[] {
  if (history === null) {
    return [];
  }

  return [
    ...history.device_series.map((series) => ({
      id: series.device_id ?? series.label,
      label: series.label,
      timestamps: series.timestamps,
      values: series.values,
    })),
    {
      id: history.total_series.device_id ?? "fleet-total",
      label: history.total_series.label,
      timestamps: history.total_series.timestamps,
      values: history.total_series.values,
      emphasis: true,
      color: "#5cd4bd",
    },
  ];
}

function buildDeviceHistorySeries(
  device: Device | null | undefined,
  history: DevicePowerHistoryResponse | null,
): PowerHistoryChartSeries[] {
  if (!device || history === null) {
    return [];
  }

  return [
    {
      id: history.device_id,
      label: device.name,
      timestamps: history.timestamps,
      values: history.values,
      emphasis: true,
      color: "#7cb8ff",
    },
  ];
}

function toLocalDateTimeInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function fromLocalDateTimeInputValue(value: string): string | undefined {
  if (!value) {
    return undefined;
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return undefined;
  }

  return parsed.toISOString();
}

function buildPresetRange(preset: Exclude<HistoryPreset, "custom">): { start: string; end: string } {
  const endDate = new Date();
  const startDate = new Date(endDate);

  switch (preset) {
    case "24h":
      startDate.setHours(startDate.getHours() - 24);
      break;
    case "7d":
      startDate.setDate(startDate.getDate() - 7);
      break;
    case "30d":
      startDate.setDate(startDate.getDate() - 30);
      break;
  }

  return {
    start: toLocalDateTimeInputValue(startDate),
    end: toLocalDateTimeInputValue(endDate),
  };
}

function downloadCsv(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function AdvancedHistoryDrawer({
  open,
  scope,
  device = null,
  onClose,
}: AdvancedHistoryDrawerProps) {
  const initialRange = useMemo(() => buildPresetRange("24h"), []);
  const [preset, setPreset] = useState<HistoryPreset>("24h");
  const [startInput, setStartInput] = useState(initialRange.start);
  const [endInput, setEndInput] = useState(initialRange.end);
  const [appliedQuery, setAppliedQuery] = useState<PowerHistoryQuery>({
    start: fromLocalDateTimeInputValue(initialRange.start),
    end: fromLocalDateTimeInputValue(initialRange.end),
    max_points: QUERY_MAX_POINTS,
  });
  const [fleetHistory, setFleetHistory] = useState<FleetPowerHistoryResponse | null>(null);
  const [deviceHistory, setDeviceHistory] = useState<DevicePowerHistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chartView, setChartView] = useState<PowerHistoryChartView | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    let cancelled = false;

    async function loadHistory() {
      setLoading(true);
      setError(null);
      try {
        if (scope === "fleet") {
          const response = await getDashboardPowerHistory(appliedQuery);
          if (!cancelled) {
            setFleetHistory(response);
            setDeviceHistory(null);
          }
          return;
        }

        if (!device) {
          throw new Error("Dispositivo non disponibile per la vista storica avanzata.");
        }

        const response = await getDevicePowerHistory(device.device_id, appliedQuery);
        if (!cancelled) {
          setDeviceHistory(response);
          setFleetHistory(null);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Impossibile caricare lo storico avanzato.",
          );
          setFleetHistory(null);
          setDeviceHistory(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadHistory();
    return () => {
      cancelled = true;
    };
  }, [appliedQuery, device, open, scope]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const nextRange = buildPresetRange("24h");
    setPreset("24h");
    setStartInput(nextRange.start);
    setEndInput(nextRange.end);
    setAppliedQuery({
      start: fromLocalDateTimeInputValue(nextRange.start),
      end: fromLocalDateTimeInputValue(nextRange.end),
      max_points: QUERY_MAX_POINTS,
    });
  }, [device?.device_id, open, scope]);

  if (!open) {
    return null;
  }

  const labels = scope === "fleet" ? fleetHistory?.labels ?? [] : deviceHistory?.labels ?? [];
  const series =
    scope === "fleet"
      ? buildFleetHistorySeries(fleetHistory)
      : buildDeviceHistorySeries(device, deviceHistory);

  const title = scope === "fleet" ? "Storico avanzato impianto" : "Storico avanzato inverter";
  const subtitle =
    scope === "fleet"
      ? "Filtra il parco inverter, confronta le serie e naviga nel tempo."
      : `${device?.name ?? "Dispositivo"} · analisi storica avanzata della potenza.`;

  function handlePresetSelect(nextPreset: Exclude<HistoryPreset, "custom">): void {
    const range = buildPresetRange(nextPreset);
    setPreset(nextPreset);
    setStartInput(range.start);
    setEndInput(range.end);
    setAppliedQuery({
      start: fromLocalDateTimeInputValue(range.start),
      end: fromLocalDateTimeInputValue(range.end),
      max_points: QUERY_MAX_POINTS,
    });
  }

  function handleApplyCustomRange(): void {
    setPreset("custom");
    setAppliedQuery({
      start: fromLocalDateTimeInputValue(startInput),
      end: fromLocalDateTimeInputValue(endInput),
      max_points: QUERY_MAX_POINTS,
    });
  }

  function handleResetFilters(): void {
    const range = buildPresetRange("24h");
    setPreset("24h");
    setStartInput(range.start);
    setEndInput(range.end);
    setAppliedQuery({
      start: fromLocalDateTimeInputValue(range.start),
      end: fromLocalDateTimeInputValue(range.end),
      max_points: QUERY_MAX_POINTS,
    });
  }

  function handleExportCsv(): void {
    if (!chartView || chartView.visibleSeries.length === 0 || chartView.labels.length === 0) {
      return;
    }

    const header = ["timestamp", ...chartView.visibleSeries.map((line) => line.label)];
    const rows = chartView.labels.map((label, index) => [
      label,
      ...chartView.visibleSeries.map((line) => {
        const value = line.values[index];
        return value === null ? "" : String(value);
      }),
    ]);
    const csv = [header, ...rows]
      .map((row) =>
        row
          .map((cell) => `"${String(cell).replace(/"/g, '""')}"`)
          .join(","),
      )
      .join("\n");

    const scopeLabel = scope === "fleet" ? "impianto" : device?.name ?? "device";
    downloadCsv(`storico_${scopeLabel}_${Date.now()}.csv`, csv);
  }

  const summaryRange =
    labels.length > 0
      ? `${dateTimeFormatter.format(new Date(labels[0]))} - ${dateTimeFormatter.format(
          new Date(labels[labels.length - 1]),
        )}`
      : "Nessun campione nell'intervallo selezionato";
  const section = SETTINGS_SECTION_CONTENT.history;

  return (
    <div className="history-explorer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className={`history-explorer-drawer settings-accent-shell ${getSettingsAccentClass(
          "history",
        )}`}
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="history-explorer-header">
          <div className="history-explorer-copy">
            <p className="panel-kicker">{section.eyebrow}</p>
            <h2>{title}</h2>
            <p>{subtitle}</p>
            <div className="settings-accent-pill-row">
              <span className={`settings-accent-pill ${getSettingsAccentClass("history")}`}>
                {section.legendLabel}
              </span>
            </div>
          </div>
          <button className="icon-button" type="button" onClick={onClose}>
            Chiudi
          </button>
        </header>

        <section className="history-explorer-panel">
          <div className="history-explorer-panel-head">
            <div>
              <p className="panel-kicker">Filtri rapidi</p>
              <h3>Intervallo di analisi</h3>
            </div>
            <span className="panel-meta">{summaryRange}</span>
          </div>

          <ul className="settings-guidance-list settings-guidance-list--tight">
            {section.guidance.map((item) => (
              <li key={`${item.label}:${item.text}`}>
                <strong>{item.label}</strong>
                <span>{item.text}</span>
              </li>
            ))}
          </ul>

          <div className="history-explorer-presets">
            {([
              ["24h", "Ultime 24h"],
              ["7d", "Ultimi 7 giorni"],
              ["30d", "Ultimi 30 giorni"],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                className={`history-explorer-preset ${
                  preset === value ? "history-explorer-preset--active" : ""
                }`}
                type="button"
                onClick={() => handlePresetSelect(value)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="history-explorer-filter-grid">
            <label className="field">
              <span className="field-label">Data inizio</span>
              <input
                className="field-control"
                type="datetime-local"
                value={startInput}
                onChange={(event) => {
                  setPreset("custom");
                  setStartInput(event.currentTarget.value);
                }}
              />
            </label>
            <label className="field">
              <span className="field-label">Data fine</span>
              <input
                className="field-control"
                type="datetime-local"
                value={endInput}
                onChange={(event) => {
                  setPreset("custom");
                  setEndInput(event.currentTarget.value);
                }}
              />
            </label>
          </div>

          <div className="history-explorer-actions">
            <button className="secondary-button" type="button" onClick={handleResetFilters}>
              Ripristina
            </button>
            <button className="secondary-button" type="button" onClick={handleExportCsv}>
              Esporta CSV
            </button>
            <button className="action-button" type="button" onClick={handleApplyCustomRange}>
              Applica filtro
            </button>
          </div>
        </section>

        <section className="history-explorer-panel">
          <div className="history-explorer-panel-head">
            <div>
              <p className="panel-kicker">Storico interattivo</p>
              <h3>Potenza nel tempo</h3>
            </div>
            <span className="panel-meta">
              Legenda cliccabile e filtro temporale nello stesso grafico
            </span>
          </div>

          <PowerHistoryChart
            labels={labels}
            series={series}
            loading={loading}
            errorMessage={error}
            emptyTitle="Nessun campione disponibile nel range selezionato"
            emptyMessage="Prova a cambiare intervallo o torna su uno dei preset rapidi per recuperare i campioni salvati."
            height={380}
            onViewChange={setChartView}
          />
        </section>
      </aside>
    </div>
  );
}
