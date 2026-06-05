import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import {
  getDevice,
  getDeviceOverview,
  getDevicePowerHistory,
  sendActivePowerLimit,
  sendDeviceCommand,
  type CommandResponse,
  type Device,
  type DeviceOverview,
  type DeviceOverviewCommandPoint,
  type DeviceOverviewTelemetryPoint,
  type DevicePowerHistoryResponse,
} from "../api";
import { AdvancedHistoryDrawer } from "./AdvancedHistoryDrawer";
import {
  PowerHistoryChart,
  type PowerHistoryChartSeries,
} from "./PowerHistoryChart";
import {
  buildOrderedTelemetrySections,
  buildTelemetryMacroGroups,
  buildTelemetrySectionNote,
  translateTelemetryLabel,
  translateTelemetrySection,
} from "../telemetryPresentation";

type DeviceDetailPanelProps = {
  deviceId: string;
  onClose: () => void;
  layout?: "overlay" | "inline";
  viewMode?: "all" | "live" | "history" | "commands";
};

const metricFormatter = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const dateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatCreatedAt(createdAt: string): string {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) {
    return createdAt;
  }

  return dateTimeFormatter.format(date);
}

function formatRuntimeTimestamp(rawValue: string | null | undefined): string {
  if (!rawValue) {
    return "Non disponibile";
  }
  const parsed = new Date(rawValue);
  if (Number.isNaN(parsed.getTime())) {
    return rawValue;
  }
  return dateTimeFormatter.format(parsed);
}

function formatDetailValue(value: string | number | boolean | null): string {
  if (value === null) {
    return "Nessuno";
  }

  return String(value);
}

function translateStatusLabel(status: string): string {
  switch (status) {
    case "online":
      return "Online";
    case "degraded":
      return "Parziale";
    case "pending":
      return "In attesa";
    case "offline":
      return "Offline";
    case "warning":
      return "Avviso";
    case "fault":
      return "Guasto";
    default:
      return status.split("_").join(" ");
  }
}

function translateCommandMessage(message: string): string {
  switch (message) {
    case "Catalog model not found for device.":
      return "Modello di catalogo non trovato per il dispositivo.";
    case "Active power limit command is not available for this model.":
      return "Il comando di limite potenza attiva non è disponibile per questo modello.";
    case "Active power setpoint is not available for this model.":
      return "Il setpoint di potenza attiva non è disponibile per questo modello.";
    case "Modbus TCP command failed.":
      return "Comando Modbus TCP non riuscito.";
    case "Modbus TCP command sent.":
      return "Comando Modbus TCP inviato correttamente.";
    case "Modbus RTU command failed.":
      return "Comando Modbus RTU non riuscito.";
    case "Modbus RTU command sent.":
      return "Comando Modbus RTU inviato correttamente.";
    default:
      return message;
  }
}

type DetailKpiCardProps = {
  label: string;
  value: string;
  note: string;
};

function DetailKpiCard({ label, value, note }: DetailKpiCardProps) {
  return (
    <article className="detail-kpi-card">
      <p className="detail-kpi-label">{label}</p>
      <strong className="detail-kpi-value">{value}</strong>
      <p className="detail-kpi-note">{note}</p>
    </article>
  );
}

type DetailCardProps = {
  label: string;
  value: string;
};

function DetailCard({ label, value }: DetailCardProps) {
  return (
    <article className="detail-card">
      <p className="detail-card-label">{label}</p>
      <strong className="detail-card-value">{value}</strong>
    </article>
  );
}

type DeviceCommandCardProps = {
  command: DeviceOverviewCommandPoint;
  value: string;
  loading: boolean;
  errorMessage: string | null;
  result: CommandResponse | null;
  onValueChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  emphasis?: boolean;
  submitLabel?: string;
};

function DeviceCommandCard({
  command,
  value,
  loading,
  errorMessage,
  result,
  onValueChange,
  onSubmit,
  emphasis = false,
  submitLabel = "Invia comando",
}: DeviceCommandCardProps) {
  const isActivePowerLimit = command.key === "active_power_limit";
  const label = isActivePowerLimit
    ? "Setpoint potenza attiva"
    : translateTelemetryLabel(command.label);

  return (
    <article
      className={`detail-command-card ${emphasis ? "detail-command-card--emphasis" : ""}`}
    >
      <form className="command-form" onSubmit={onSubmit}>
        <label className="field">
          <span className="field-label">{label}</span>
          <input
            className="field-control"
            type="number"
            min={command.min_value ?? undefined}
            max={command.max_value ?? undefined}
            step={command.step ?? undefined}
            value={value}
            onChange={(event) => onValueChange(event.currentTarget.value)}
            placeholder={command.max_value?.toString() ?? command.unit ?? "valore"}
            disabled={loading}
          />
        </label>
        <button className="action-button" type="submit" disabled={loading}>
          {loading ? "Invio..." : submitLabel}
        </button>
      </form>
      <p className="detail-empty">{buildCommandRangeNote(command)}</p>
      {errorMessage ? <div className="panel-state panel-state--error">{errorMessage}</div> : null}
      {result ? (
        <div
          className={`command-feedback command-feedback--${
            result.success ? "success" : "failure"
          }`}
        >
          <p className="command-feedback-label">Esito comando</p>
          <strong className="command-feedback-message">
            {translateCommandMessage(result.message)}
          </strong>
          <div className="command-feedback-meta">
            {Object.entries(result.diagnostics).map(([key, diagnosticValue]) => (
              <span key={key} className="command-feedback-chip">
                {key}: {formatDetailValue(diagnosticValue)}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function buildDeviceHistorySeries(
  device: Device | null,
  powerHistory: DevicePowerHistoryResponse | null,
): PowerHistoryChartSeries[] {
  if (device === null || powerHistory === null) {
    return [];
  }

  return [
    {
      id: powerHistory.device_id,
      label: device.name,
      timestamps: powerHistory.timestamps,
      values: powerHistory.values,
      emphasis: true,
      color: "#7cb8ff",
    },
  ];
}

function formatTelemetryValue(point: DeviceOverviewTelemetryPoint): string {
  return point.unit ? `${point.display_value} ${point.unit}` : point.display_value;
}

function formatMetricValue(value: number, unit: string): string {
  return `${metricFormatter.format(value)} ${unit}`;
}

function buildCommandRangeNote(command: DeviceOverviewCommandPoint): string {
  const parts: string[] = [];
  if (command.min_value !== null) {
    parts.push(`min ${command.min_value}`);
  }
  if (command.max_value !== null) {
    parts.push(`max ${command.max_value}`);
  }
  if (command.step !== null) {
    parts.push(`step ${command.step}`);
  }
  if (parts.length === 0) {
    return "Scrittura parametro numerico";
  }

  return parts.join(" | ");
}

function formatActiveProfile(device: Device): string {
  return `${device.brand} | ${device.model} | ${device.protocol}`;
}

export function DeviceDetailPanel({
  deviceId,
  onClose,
  layout = "overlay",
  viewMode = "all",
}: DeviceDetailPanelProps) {
  const isInline = layout === "inline";
  const showLiveSections = viewMode === "all" || viewMode === "live";
  const showHistorySection = viewMode === "all" || viewMode === "history";
  const showCommandSection = viewMode === "all" || viewMode === "commands";
  const [device, setDevice] = useState<Device | null>(null);
  const [overview, setOverview] = useState<DeviceOverview | null>(null);
  const [powerHistory, setPowerHistory] = useState<DevicePowerHistoryResponse | null>(null);
  const [powerHistoryError, setPowerHistoryError] = useState<string | null>(null);
  const [commandValues, setCommandValues] = useState<Record<string, string>>({});
  const [commandLoadingKey, setCommandLoadingKey] = useState<string | null>(null);
  const [commandErrors, setCommandErrors] = useState<Record<string, string>>({});
  const [commandResults, setCommandResults] = useState<Record<string, CommandResponse>>({});
  const [showAdvancedDetails, setShowAdvancedDetails] = useState(false);
  const [showAdvancedCommands, setShowAdvancedCommands] = useState(false);
  const [showAdvancedHistory, setShowAdvancedHistory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const isMountedRef = useRef(true);
  const activeDeviceIdRef = useRef(deviceId);
  const requestInFlightRef = useRef(false);

  async function loadDeviceDetail(showLoading = true) {
    if (requestInFlightRef.current) {
      return;
    }

    requestInFlightRef.current = true;
    const requestedDeviceId = activeDeviceIdRef.current;
    if (showLoading && isMountedRef.current) {
      setLoading(true);
    }
    if (isMountedRef.current) {
      setError(null);
    }

    try {
      const [deviceResult, overviewResult, historyResult] = await Promise.allSettled([
        getDevice(requestedDeviceId),
        getDeviceOverview(requestedDeviceId),
        getDevicePowerHistory(requestedDeviceId),
      ]);

      if (deviceResult.status === "rejected") {
        throw deviceResult.reason;
      }

      if (overviewResult.status === "rejected") {
        throw overviewResult.reason;
      }

      if (!isMountedRef.current || activeDeviceIdRef.current !== requestedDeviceId) {
        return;
      }

      setDevice(deviceResult.value);
      setOverview(overviewResult.value);
      if (historyResult.status === "fulfilled") {
        setPowerHistory(historyResult.value);
        setPowerHistoryError(null);
      } else {
        setPowerHistoryError(
          historyResult.reason instanceof Error
            ? historyResult.reason.message
            : "Impossibile caricare lo storico di potenza del dispositivo.",
        );
      }
    } catch (loadError) {
      if (!isMountedRef.current || activeDeviceIdRef.current !== requestedDeviceId) {
        return;
      }

      setDevice(null);
      setOverview(null);
      setPowerHistory(null);
      setPowerHistoryError(null);
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Impossibile caricare il dettaglio del dispositivo.",
      );
    } finally {
      requestInFlightRef.current = false;
      if (
        showLoading &&
        isMountedRef.current &&
        activeDeviceIdRef.current === requestedDeviceId
      ) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    isMountedRef.current = true;
    activeDeviceIdRef.current = deviceId;
    setCommandValues({});
    setCommandLoadingKey(null);
    setCommandErrors({});
    setPowerHistory(null);
    setPowerHistoryError(null);
    setCommandResults({});
    setShowAdvancedDetails(false);
    setShowAdvancedCommands(false);
    setShowAdvancedHistory(false);

    void loadDeviceDetail();

    const intervalId = window.setInterval(() => {
      void loadDeviceDetail(false);
    }, 5000);

    return () => {
      isMountedRef.current = false;
      window.clearInterval(intervalId);
    };
  }, [deviceId]);

  async function handleCommandSubmit(
    event: FormEvent<HTMLFormElement>,
    command: DeviceOverviewCommandPoint,
  ) {
    event.preventDefault();

    if (!device) {
      return;
    }

    const trimmedValue = (commandValues[command.key] ?? "").trim();
    const numericValue = Number(trimmedValue);
    if (!trimmedValue || !Number.isFinite(numericValue)) {
      setCommandResults((current) => {
        const next = { ...current };
        delete next[command.key];
        return next;
      });
      setCommandErrors((current) => ({
        ...current,
        [command.key]: "Inserisci un valore numerico valido per il parametro selezionato.",
      }));
      return;
    }

    setCommandLoadingKey(command.key);
    setCommandErrors((current) => {
      const next = { ...current };
      delete next[command.key];
      return next;
    });
    setCommandResults((current) => {
      const next = { ...current };
      delete next[command.key];
      return next;
    });

    try {
      const response = await sendDeviceCommand(device.device_id, command.key, {
        value: numericValue,
      });
      setCommandResults((current) => ({ ...current, [command.key]: response }));
    } catch (submitError) {
      setCommandErrors((current) => ({
        ...current,
        [command.key]:
          submitError instanceof Error
            ? submitError.message
            : "Impossibile inviare il comando selezionato.",
      }));
    } finally {
      setCommandLoadingKey(null);
    }
  }

  async function handlePrimaryActivePowerSubmit(
    event: FormEvent<HTMLFormElement>,
    command: DeviceOverviewCommandPoint,
  ) {
    event.preventDefault();

    if (!device) {
      return;
    }

    const trimmedValue = (commandValues[command.key] ?? "").trim();
    const numericValue = Number(trimmedValue);
    if (!trimmedValue || !Number.isFinite(numericValue)) {
      setCommandResults((current) => {
        const next = { ...current };
        delete next[command.key];
        return next;
      });
      setCommandErrors((current) => ({
        ...current,
        [command.key]: "Inserisci un valore percentuale valido tra 0 e 100.",
      }));
      return;
    }

    setCommandLoadingKey(command.key);
    setCommandErrors((current) => {
      const next = { ...current };
      delete next[command.key];
      return next;
    });
    setCommandResults((current) => {
      const next = { ...current };
      delete next[command.key];
      return next;
    });

    try {
      const response = await sendActivePowerLimit(device.device_id, { value: numericValue });
      setCommandResults((current) => ({ ...current, [command.key]: response }));
    } catch (submitError) {
      setCommandErrors((current) => ({
        ...current,
        [command.key]:
          submitError instanceof Error
            ? submitError.message
            : "Impossibile inviare il setpoint di potenza attiva.",
      }));
    } finally {
      setCommandLoadingKey(null);
    }
  }

  const telemetrySections = overview ? buildOrderedTelemetrySections(overview.telemetry) : [];
  const telemetryMacroGroups = overview ? buildTelemetryMacroGroups(overview.telemetry) : [];
  const hasAdvancedTelemetry = telemetrySections.length > 0;
  const primaryPowerCommand =
    overview?.commands.find((command) => command.key === "active_power_limit") ?? null;
  const secondaryCommands = overview
    ? overview.commands.filter((command) => command.key !== "active_power_limit")
    : [];
  const showPrimaryPowerCommand = primaryPowerCommand !== null && viewMode !== "history";

  const content: ReactNode = (
    <>
      <div className="modal-header">
        <div className="modal-title-group">
          <p className="panel-kicker">Dettaglio impianto</p>
          <h2 id="device-detail-title">Dettaglio dispositivo</h2>
          <p className="modal-copy">
            Configurazione in tempo reale, metriche e diagnostica per l&apos;inverter selezionato.
          </p>
        </div>
        <button className="icon-button" type="button" onClick={onClose}>
          {isInline ? "Torna all'impianto" : "Chiudi"}
        </button>
      </div>

      <div className="detail-content">
        {loading ? (
          <div className="panel-state">
            Caricamento dettaglio dispositivo dal backend...
          </div>
        ) : null}
        {error ? <div className="panel-state panel-state--error">{error}</div> : null}

        {!loading && !error && device && overview ? (
          <>
            <section className="detail-hero detail-hero--priority">
              <div className="detail-hero-primary">
                <p className="panel-kicker">Dispositivo selezionato</p>
                <h2>{device.name}</h2>
                <p className="detail-copy">
                  {device.brand} | {device.model}
                </p>
                <div className="detail-profile-banner">
                  <span className="detail-profile-banner__label">Profilo attivo</span>
                  <strong className="detail-profile-banner__value">
                    {formatActiveProfile(device)}
                  </strong>
                  <span className="detail-profile-banner__note">
                    Trasporto {device.transport}
                  </span>
                </div>
                <div className="detail-hero-status-row">
                  <span className={`status-badge status-badge--${device.status.toLowerCase()}`}>
                    {translateStatusLabel(device.status)}
                  </span>
                  <span className="detail-hero-meta">
                    {device.protocol} | {device.transport}
                  </span>
                </div>
              </div>
              <div className="detail-hero-side">
                <div className="detail-hero-power">
                  <span className="detail-hero-power-label">Potenza attuale</span>
                  <strong>{formatMetricValue(overview.metrics.power_kw, "kW")}</strong>
                </div>
                {showPrimaryPowerCommand ? (
                  <div className="detail-primary-command">
                    <p className="detail-hero-power-label">Setpoint potenza attiva</p>
                    <DeviceCommandCard
                      command={primaryPowerCommand}
                      value={commandValues[primaryPowerCommand.key] ?? ""}
                      loading={commandLoadingKey === primaryPowerCommand.key}
                      errorMessage={commandErrors[primaryPowerCommand.key] ?? null}
                      result={commandResults[primaryPowerCommand.key] ?? null}
                      onValueChange={(nextValue) =>
                        setCommandValues((current) => ({
                          ...current,
                          [primaryPowerCommand.key]: nextValue,
                        }))
                      }
                      onSubmit={(event) =>
                        void handlePrimaryActivePowerSubmit(event, primaryPowerCommand)
                      }
                      emphasis
                      submitLabel="Applica setpoint"
                    />
                  </div>
                ) : null}
              </div>
            </section>

            {showLiveSections ? (
              <>
                <section className="detail-section">
                  <div className="detail-kpi-grid">
                    <DetailKpiCard
                      label="Energia giornaliera"
                      value={formatMetricValue(overview.metrics.daily_energy_kwh, "kWh")}
                      note="Ultimo overview disponibile"
                    />
                    <DetailKpiCard
                      label="Energia totale"
                      value={formatMetricValue(overview.metrics.total_energy_kwh, "kWh")}
                      note="Valore cumulato disponibile"
                    />
                    <DetailKpiCard
                      label="Temperatura"
                      value={formatMetricValue(overview.metrics.temperature_c, "C")}
                      note="Lettura termica istantanea"
                    />
                    <DetailKpiCard
                      label="Tempo di risposta"
                      value={`${overview.diagnostics.response_time_ms} ms`}
                      note="Tempo medio dell'ultimo polling"
                    />
                    <DetailKpiCard
                      label="Ultimo dato valido"
                      value={formatRuntimeTimestamp(overview.diagnostics.last_valid_data_at)}
                      note="Timestamp del dataset completo piu recente"
                    />
                  </div>
                </section>

              </>
            ) : null}

            {showHistorySection ? (
            <section className="detail-section">
              <div className="detail-section-head">
                <div>
                  <h3 className="detail-section-title">Storico potenza attiva</h3>
                </div>
                <div className="stage-header-actions">
                  <span className="detail-section-meta">Campioni reali dal polling</span>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => setShowAdvancedHistory(true)}
                  >
                    Storico avanzato
                  </button>
                </div>
              </div>
              <PowerHistoryChart
                labels={powerHistory?.labels ?? []}
                series={buildDeviceHistorySeries(device, powerHistory)}
                loading={loading}
                errorMessage={powerHistoryError}
                emptyTitle="Storico inverter non ancora disponibile"
                emptyMessage="Il backend non ha ancora restituito campioni storici reali di potenza per questo inverter. Il grafico si popolerà automaticamente con i prossimi campioni del polling."
                height={300}
              />
            </section>

            ) : null}

            {showLiveSections ? (
              <>
                <section className="detail-section detail-section--progressive">
                  <div className="detail-progressive-head">
                    <div>
                      <p className="panel-kicker">Vista semplificata</p>
                      <h3 className="detail-section-title">Dati aggiuntivi del dispositivo</h3>
                      <p className="detail-progressive-copy">
                        Stato, KPI, storico e comandi restano subito visibili. Apri questo
                        blocco solo quando ti serve consultare tutta la telemetria tecnica.
                      </p>
                    </div>
                    <button
                      className="secondary-button detail-progressive-toggle"
                      type="button"
                      onClick={() => setShowAdvancedDetails((current) => !current)}
                    >
                      {showAdvancedDetails ? "Nascondi dettagli avanzati" : "Mostra dettagli avanzati"}
                    </button>
                  </div>

                  {showAdvancedDetails ? (
                    <div className="detail-advanced-stack">
                      <div className="detail-advanced-grid">
                        <section className="detail-advanced-card">
                          <div className="detail-section-head">
                            <h3 className="detail-section-title">Profilo dispositivo</h3>
                            <span className="detail-section-meta">Dati base e censimento</span>
                          </div>
                          <div className="detail-grid">
                            <DetailCard label="Marchio" value={device.brand} />
                            <DetailCard label="Modello" value={device.model} />
                            <DetailCard label="Protocollo" value={device.protocol} />
                            <DetailCard label="Trasporto" value={device.transport} />
                            <DetailCard label="Stato" value={translateStatusLabel(device.status)} />
                            <DetailCard label="Creato il" value={formatCreatedAt(device.created_at)} />
                          </div>
                        </section>

                        <section className="detail-advanced-card">
                          <div className="detail-section-head">
                            <h3 className="detail-section-title">Diagnostica polling</h3>
                            <span className="detail-section-meta">Salute della comunicazione</span>
                          </div>
                          <div className="detail-grid">
                            <DetailCard
                              label="Ultimo stato polling"
                              value={overview.diagnostics.last_poll_status}
                            />
                            <DetailCard
                              label="Tempo di risposta"
                              value={`${overview.diagnostics.response_time_ms} ms`}
                            />
                            <DetailCard
                              label="Tentativi"
                              value={String(overview.diagnostics.retries)}
                            />
                            <DetailCard
                              label="Ultimo errore"
                              value={formatDetailValue(overview.diagnostics.last_error)}
                            />
                            <DetailCard
                              label="Ultimo contatto"
                              value={formatRuntimeTimestamp(overview.diagnostics.last_contact_at)}
                            />
                            <DetailCard
                              label="Ultimo dato valido"
                              value={formatRuntimeTimestamp(overview.diagnostics.last_valid_data_at)}
                            />
                            <DetailCard
                              label="Stato comunicazione"
                              value={overview.diagnostics.communication_state}
                            />
                            <DetailCard
                              label="Freschezza dati"
                              value={overview.diagnostics.data_freshness}
                            />
                          </div>
                        </section>
                      </div>

                      <section className="detail-section">
                        <div className="detail-section-head">
                          <h3 className="detail-section-title">Telemetria completa</h3>
                          <span className="detail-section-meta">Raggruppata in macro categorie</span>
                        </div>
                        {hasAdvancedTelemetry ? (
                          <div className="detail-macro-stack">
                            {telemetryMacroGroups.map((group) => (
                              <section key={group.key} className="detail-macro-group">
                                <div className="detail-macro-group-head">
                                  <div>
                                    <p className="panel-kicker">{group.title}</p>
                                    <p className="detail-macro-group-note">{group.note}</p>
                                  </div>
                                  <span className="detail-telemetry-count">
                                    {group.pointCount} valori
                                  </span>
                                </div>
                                <div className="detail-telemetry-stack detail-telemetry-stack--nested">
                                  {group.sections.map((section) => (
                                    <div key={section.section} className="detail-telemetry-section">
                                      <div className="detail-telemetry-section-head">
                                        <div>
                                          <p className="panel-kicker">
                                            {translateTelemetrySection(section.section)}
                                          </p>
                                          <p className="detail-telemetry-note">
                                            {buildTelemetrySectionNote(section.section)}
                                          </p>
                                        </div>
                                        <span className="detail-telemetry-count">
                                          {section.points.length} valori
                                        </span>
                                      </div>
                                      <div className="detail-grid detail-grid--telemetry">
                                        {section.points.map((point) => (
                                          <DetailCard
                                            key={point.key}
                                            label={translateTelemetryLabel(point.label)}
                                            value={formatTelemetryValue(point)}
                                          />
                                        ))}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </section>
                            ))}
                          </div>
                        ) : (
                          <p className="detail-empty">
                            Nessun punto di telemetria disponibile per questo modello.
                          </p>
                        )}
                      </section>
                    </div>
                  ) : (
                    <p className="detail-empty">
                      I dati tecnici completi restano nascosti per mantenere la vista piu'
                      semplice. Apri i dettagli avanzati solo per analisi, assistenza o
                      diagnostica approfondita.
                    </p>
                  )}
                </section>
              </>
            ) : null}

            {showCommandSection ? (
              <section className="detail-section detail-section--progressive">
                <div className="detail-progressive-head">
                  <div>
                    <p className="panel-kicker">Comandi avanzati</p>
                    <h3 className="detail-section-title">Altri comandi disponibili</h3>
                    <p className="detail-progressive-copy">
                      Il setpoint di potenza attiva resta sempre in primo piano. Gli altri
                      comandi sono raccolti qui per evitare errori e mantenere la vista piu'
                      semplice durante l'uso normale.
                    </p>
                  </div>
                  {secondaryCommands.length > 0 ? (
                    <button
                      className="secondary-button detail-progressive-toggle"
                      type="button"
                      onClick={() => setShowAdvancedCommands((current) => !current)}
                    >
                      {showAdvancedCommands ? "Nascondi altri comandi" : "Mostra altri comandi"}
                    </button>
                  ) : null}
                </div>
                {secondaryCommands.length > 0 ? (
                  showAdvancedCommands ? (
                    <div className="detail-command-stack">
                      {secondaryCommands.map((command) => (
                        <DeviceCommandCard
                          key={command.key}
                          command={command}
                          value={commandValues[command.key] ?? ""}
                          loading={commandLoadingKey === command.key}
                          errorMessage={commandErrors[command.key] ?? null}
                          result={commandResults[command.key] ?? null}
                          onValueChange={(nextValue) =>
                            setCommandValues((current) => ({
                              ...current,
                              [command.key]: nextValue,
                            }))
                          }
                          onSubmit={(event) => void handleCommandSubmit(event, command)}
                        />
                      ))}
                    </div>
                  ) : (
                    <p className="detail-empty">
                      Altri {secondaryCommands.length} comandi disponibili ma nascosti per
                      mantenere la vista operativa piu' pulita.
                    </p>
                  )
                ) : (
                  <p className="detail-empty">
                    Nessun comando aggiuntivo disponibile oltre al setpoint di potenza attiva.
                  </p>
                )}
              </section>
            ) : null}
          </>
        ) : null}
      </div>
      <AdvancedHistoryDrawer
        open={showAdvancedHistory}
        scope="device"
        device={device}
        onClose={() => setShowAdvancedHistory(false)}
      />
    </>
  );

  if (isInline) {
    return <section className="detail-inline-shell">{content}</section>;
  }

  return (
    <div className="detail-backdrop">
      <aside
        aria-labelledby="device-detail-title"
        aria-modal="true"
        className="detail-panel"
        role="dialog"
      >
        {content}
      </aside>
    </div>
  );
}
