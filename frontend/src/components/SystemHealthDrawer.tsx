import type {
  SystemHealthBroadcastGroup,
  SystemHealthEndpointRuntime,
  SystemHealthResponse,
} from "../api";
import { getSettingsAccentClass, SETTINGS_SECTION_CONTENT } from "../settingsSections";
import { getSerialPortDisplayName } from "./deviceProvisioningShared";

type SystemHealthDrawerProps = {
  health: SystemHealthResponse | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
};

const metricFormatter = new Intl.NumberFormat("it-IT", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function formatBytes(bytes: number): string {
  const absolute = Math.abs(bytes);
  if (absolute >= 1024 ** 3) {
    return `${metricFormatter.format(bytes / 1024 ** 3)} GB`;
  }
  if (absolute >= 1024 ** 2) {
    return `${metricFormatter.format(bytes / 1024 ** 2)} MB`;
  }
  if (absolute >= 1024) {
    return `${metricFormatter.format(bytes / 1024)} KB`;
  }
  return `${bytes} B`;
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "--";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("it-IT");
}

function formatDurationMs(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "--";
  }
  if (value >= 1000) {
    return `${metricFormatter.format(value / 1000)} s`;
  }
  return `${Math.round(value)} ms`;
}

function formatDurationSeconds(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "--";
  }
  return `${metricFormatter.format(value)} s`;
}

function formatSloState(state: SystemHealthEndpointRuntime["active_power_slo_state"]): string {
  switch (state) {
    case "pass":
      return "Entro obiettivo";
    case "warning":
      return "Vicino al limite";
    case "fail":
      return "Fuori obiettivo";
    default:
      return "Da misurare";
  }
}

function buildHealthTone(health: SystemHealthResponse | null): "positive" | "warning" | "neutral" {
  if (!health) {
    return "neutral";
  }
  if (
    !health.polling.running ||
    health.polling.consecutive_loop_error_count > 0 ||
    health.modbus_tcp_slave.startup_error !== null ||
    health.status_counts.offline > 0
  ) {
    return "warning";
  }
  return "positive";
}

function getRuntimeStatePriority(runtime: SystemHealthEndpointRuntime): number {
  switch (runtime.state) {
    case "cooldown":
      return 0;
    case "degraded":
      return 1;
    case "healthy":
      return 2;
    default:
      return 3;
  }
}

function buildRuntimeTone(
  runtime: SystemHealthEndpointRuntime,
): "positive" | "warning" | "neutral" {
  if (
    runtime.state === "cooldown" ||
    runtime.state === "degraded" ||
    runtime.offline_count > 0
  ) {
    return "warning";
  }
  if (runtime.state === "healthy") {
    return "positive";
  }
  return "neutral";
}

function buildRuntimeStateLabel(runtime: SystemHealthEndpointRuntime): string {
  switch (runtime.state) {
    case "cooldown":
      return "Riconnessione";
    case "degraded":
      return "Da verificare";
    case "healthy":
      return runtime.shared ? "Condiviso stabile" : "Stabile";
    default:
      return "In attesa";
  }
}

function buildRuntimeTypeLabel(runtime: SystemHealthEndpointRuntime): string {
  return runtime.endpoint_type === "tcp" ? "Gateway TCP" : "Bus RS485";
}

function buildRuntimeEndpointLabel(runtime: SystemHealthEndpointRuntime): string {
  return runtime.endpoint_type === "serial"
    ? getSerialPortDisplayName(runtime.endpoint_label)
    : runtime.endpoint_label;
}

function buildRuntimeStatusSummary(runtime: SystemHealthEndpointRuntime): string {
  const parts = [`${runtime.online_count} online`];
  if (runtime.pending_count > 0) {
    parts.push(`${runtime.pending_count} in attesa`);
  }
  if (runtime.offline_count > 0) {
    parts.push(`${runtime.offline_count} offline`);
  }
  return parts.join(" | ");
}

function compactRuntimeMessage(value: string | null): string | null {
  if (!value) {
    return null;
  }

  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > 120 ? `${normalized.slice(0, 117)}...` : normalized;
}

function buildRuntimeNote(runtime: SystemHealthEndpointRuntime): string {
  const errorMessage = compactRuntimeMessage(runtime.last_error);

  if (runtime.state === "cooldown") {
    const retryLabel =
      runtime.remaining_backoff_seconds > 0
        ? `Nuovo tentativo tra ${runtime.remaining_backoff_seconds} s.`
        : "Nuovo tentativo al prossimo ciclo utile.";
    return errorMessage ? `${retryLabel} Ultimo errore: ${errorMessage}` : retryLabel;
  }

  if (runtime.state === "degraded") {
    return errorMessage ?? "L'endpoint ha avuto letture recenti non riuscite e richiede verifica.";
  }

  if (runtime.quarantined_device_count > 0) {
    return `${runtime.quarantined_device_count} slave isolati temporaneamente; gli altri continuano il ciclo.`;
  }

  if (runtime.adaptive_mode === "slow_gateway") {
    return "Gateway condiviso lento: priorita alla potenza attiva e full telemetry diluita.";
  }

  if (runtime.priority_pending) {
    return "Finestra comando attiva: polling sospeso per liberare la connessione.";
  }

  if (runtime.shared) {
    return "Endpoint condiviso ma stabile.";
  }

  return "Endpoint dedicato stabile.";
}

function buildRuntimeSchedulerSummary(runtime: SystemHealthEndpointRuntime): string {
  if (runtime.endpoint_type === "tcp") {
    if (runtime.polling_profile === "gateway_tcp_light") {
      return [
        `active ${runtime.queued_heartbeat_due_count}`,
        `full ${runtime.queued_full_due_count}`,
        `priorita ${runtime.priority_deferral_count}`,
      ].join(" | ");
    }
    return "TCP dedicato.";
  }
  return [
    `Code full ${runtime.queued_full_due_count}`,
    `heartbeat ${runtime.queued_heartbeat_due_count}`,
    `priorita ${runtime.priority_deferral_count}`,
  ].join(" | ");
}

function buildBroadcastTypeLabel(group: SystemHealthBroadcastGroup): string {
  switch (group.endpoint_type) {
    case "serial":
      return "RTU seriale";
    case "rtu_over_tcp":
      return "RTU-over-TCP";
    case "modbus_tcp_gateway":
      return "Modbus TCP";
    default:
      return "Non gestito";
  }
}

function buildBroadcastTone(group: SystemHealthBroadcastGroup): "positive" | "warning" | "neutral" {
  if (group.state === "ready") {
    return "positive";
  }
  if (group.state === "blocked" || group.state === "warning") {
    return "warning";
  }
  return "neutral";
}

function buildBroadcastBadge(group: SystemHealthBroadcastGroup): string {
  switch (group.state) {
    case "ready":
      return "Broadcast pronto";
    case "warning":
      return "Da verificare";
    case "blocked":
      return "Fallback per-device";
    default:
      return "Dedicato";
  }
}

export function SystemHealthDrawer({
  health,
  loading,
  error,
  onClose,
}: SystemHealthDrawerProps) {
  const tone = buildHealthTone(health);
  const endpointRuntimeItems = (health?.endpoint_runtimes ?? [])
    .filter((runtime) => runtime.shared || runtime.state === "degraded" || runtime.state === "cooldown")
    .slice()
    .sort((left, right) => {
      const stateDelta = getRuntimeStatePriority(left) - getRuntimeStatePriority(right);
      if (stateDelta !== 0) {
        return stateDelta;
      }

      const sharedDelta = Number(right.shared) - Number(left.shared);
      if (sharedDelta !== 0) {
        return sharedDelta;
      }

      return right.device_count - left.device_count;
    });
  const broadcastGroups = (health?.broadcast_groups ?? [])
    .slice()
    .sort((left, right) => {
      const statePriority = { blocked: 0, warning: 1, ready: 2, not_applicable: 3 };
      const stateDelta = statePriority[left.state] - statePriority[right.state];
      if (stateDelta !== 0) {
        return stateDelta;
      }
      return right.device_count - left.device_count;
    });
  const historyUsagePercent = Math.max(
    0,
    Math.min(health?.history_storage.usage_percent ?? 0, 100),
  );
  const section = SETTINGS_SECTION_CONTENT.health;

  return (
    <div
      className="focus-drawer-backdrop"
      role="presentation"
      onClick={onClose}
    >
      <aside
        className={`focus-drawer-panel system-health-drawer-panel settings-accent-shell ${getSettingsAccentClass(
          "health",
        )}`}
        aria-label="Health del sistema"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="system-health-shell">
          <header className="focus-drawer-header">
            <div>
              <p className="panel-kicker">{section.eyebrow}</p>
              <h2>{section.drawerTitle}</h2>
              <p className="focus-drawer-copy">{section.drawerCopy}</p>
              <div className="settings-accent-pill-row">
                <span className={`settings-accent-pill ${getSettingsAccentClass("health")}`}>
                  {section.legendLabel}
                </span>
              </div>
            </div>
            <button className="icon-button" type="button" onClick={onClose}>
              Chiudi
            </button>
          </header>

          <ul className="settings-guidance-list settings-guidance-list--tight">
            {section.guidance.map((item) => (
              <li key={`${item.label}:${item.text}`}>
                <strong>{item.label}</strong>
                <span>{item.text}</span>
              </li>
            ))}
          </ul>

          {loading ? <div className="panel-state">Caricamento health del sistema...</div> : null}
          {error ? <div className="panel-state panel-state--error">{error}</div> : null}

          {health ? (
            <>
              <section className="system-health-hero-grid">
                <article className="system-health-card">
                  <p className="system-health-card-label">Edge device</p>
                  <strong>{health.identity.edge_id}</strong>
                  <span>{health.identity.hostname}</span>
                  <small>
                    Build {health.identity.build_label}
                    {health.identity.build_commit ? ` | ${health.identity.build_commit}` : ""}
                  </small>
                </article>

                <article className={`system-health-card system-health-card--${tone}`}>
                  <p className="system-health-card-label">Polling engine</p>
                  <strong>{health.polling.running ? "Attivo" : "Fermo"}</strong>
                  <span>
                    {health.polling.last_cycle_duration_ms != null
                      ? `${health.polling.last_cycle_duration_ms} ms ultimo ciclo`
                      : "Nessun ciclo completato"}
                  </span>
                  <small>
                    {health.polling.consecutive_loop_error_count > 0
                      ? `Watchdog: ${health.polling.consecutive_loop_error_count} errori consecutivi`
                      : `Thread avviato ${health.polling.thread_start_count} volte`}
                  </small>
                </article>

                <article className="system-health-card">
                  <p className="system-health-card-label">Runtime dispositivi</p>
                  <strong>{health.status_counts.online}/{health.status_counts.total}</strong>
                  <span>online sul totale configurato</span>
                  <small>
                    Offline {health.status_counts.offline} | Warning {health.status_counts.warning} | Fault {health.status_counts.fault}
                  </small>
                </article>

                <article className="system-health-card">
                  <p className="system-health-card-label">Cache live</p>
                  <strong>{health.live_cache.entry_count}</strong>
                  <span>entry correnti in memoria</span>
                  <small>
                    {health.live_cache.power_history_sample_count} campioni power live buffer
                  </small>
                </article>
              </section>

              <section className="system-health-hero-grid">
                <article className="system-health-card">
                  <p className="system-health-card-label">Storico persistente</p>
                  <strong>{formatBytes(health.history_storage.current_bytes)}</strong>
                  <span>
                    su {formatBytes(health.history_storage.max_bytes)} disponibili
                  </span>
                  <small>{health.history_storage.row_count} campioni su file storico</small>
                  <div className="system-health-progress" aria-hidden="true">
                    <span style={{ width: `${historyUsagePercent}%` }} />
                  </div>
                </article>

                <article className="system-health-card">
                  <p className="system-health-card-label">Backend</p>
                  <strong>{health.identity.app_version}</strong>
                  <span>Avvio {formatTimestamp(health.identity.backend_started_at)}</span>
                  <small>{health.identity.backend_path}</small>
                </article>

                <article className="system-health-card">
                  <p className="system-health-card-label">Identita sorgente</p>
                  <strong>{health.identity.edge_id_source}</strong>
                  <span>{health.identity.build_time ?? "Build time non impostato"}</span>
                  <small>{health.identity.platform}</small>
                </article>
              </section>

              <section className="system-health-section">
                <div className="rail-section-header">
                  <div>
                    <p className="panel-kicker">Qualita e tempi</p>
                    <h2>Garanzie operative</h2>
                  </div>
                  <span className="panel-meta">
                    Valida i dati prima dei riepiloghi e misura i tempi attesi di aggiornamento.
                  </span>
                </div>

                <div className="system-health-meta-grid">
                  <article
                    className={`system-health-meta-card ${
                      health.data_quality.invalid_points > 0 ? "system-health-card--warning" : ""
                    }`}
                  >
                    <p>Qualita telemetria</p>
                    <strong>
                      {health.data_quality.valid_points}/{health.data_quality.total_points}
                    </strong>
                    <span>punti validi nell'ultimo dato completo</span>
                    <small>
                      Invalidi {health.data_quality.invalid_points} | warning{" "}
                      {health.data_quality.warning_points} | assenti{" "}
                      {health.data_quality.unavailable_points}
                    </small>
                  </article>
                  <article className="system-health-meta-card">
                    <p>SLO potenza attiva</p>
                    <strong>{health.service_levels.active_power_within_target}</strong>
                    <span>
                      device entro {formatDurationSeconds(health.service_levels.active_power_target_seconds)}
                    </span>
                    <small>
                      Fuori obiettivo {health.service_levels.active_power_over_target} | da misurare{" "}
                      {health.service_levels.active_power_unknown}
                    </small>
                  </article>
                  <article className="system-health-meta-card">
                    <p>SLO telemetria completa</p>
                    <strong>{health.service_levels.full_telemetry_within_target}</strong>
                    <span>
                      device entro {formatDurationSeconds(health.service_levels.full_telemetry_target_seconds)}
                    </span>
                    <small>
                      Fuori obiettivo {health.service_levels.full_telemetry_over_target} | da misurare{" "}
                      {health.service_levels.full_telemetry_unknown}
                    </small>
                  </article>
                  <article className="system-health-meta-card">
                    <p>Obiettivo comando</p>
                    <strong>{formatDurationSeconds(health.service_levels.command_target_seconds)}</strong>
                    <span>tempo massimo operativo desiderato</span>
                    <small>Comandi diretti in audit; dispatch flotta registrati in forma aggregata</small>
                  </article>
                </div>

                {health.data_quality.issue_devices.length > 0 ? (
                  <div className="system-health-runtime-list">
                    {health.data_quality.issue_devices.slice(0, 8).map((device) => (
                      <article
                        key={device.device_id}
                        className="system-health-runtime-card system-health-runtime-card--warning"
                      >
                        <div className="system-health-runtime-head">
                          <div>
                            <p className="system-health-runtime-kicker">Qualita dati</p>
                            <strong>{device.name}</strong>
                          </div>
                          <span className="system-health-runtime-badge system-health-runtime-badge--warning">
                            {device.invalid_count} invalidi
                          </span>
                        </div>
                        <p className="system-health-runtime-note">
                          Warning {device.warning_count} | non disponibili {device.unavailable_count}
                        </p>
                        <div className="system-health-runtime-devices">
                          {device.examples.map((example) => (
                            <span key={example} className="system-health-chip system-health-chip--warning">
                              {example}
                            </span>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="detail-empty">
                    Nessuna anomalia rilevata nei punti di telemetria disponibili.
                  </div>
                )}
              </section>

              <section className="system-health-section">
                <div className="rail-section-header">
                  <div>
                    <p className="panel-kicker">Servizi runtime</p>
                    <h2>Diagnostica operativa</h2>
                  </div>
                  <span className="panel-meta">
                    Snapshot generato il {formatTimestamp(health.generated_at)}
                  </span>
                </div>

                <div className="system-health-meta-grid">
                  <article className="system-health-meta-card">
                    <p>Scheduling</p>
                    <strong>{health.polling.scheduled_device_count}</strong>
                    <span>device pianificati</span>
                    <small>{health.polling.pollable_device_count} pollabili</small>
                  </article>
                  <article className="system-health-meta-card">
                    <p>Ultimo ciclo</p>
                    <strong>{formatTimestamp(health.polling.last_cycle_completed_at)}</strong>
                    <span>completamento</span>
                    <small>
                      {health.polling.last_due_device_count} device scaduti | prossimo full{" "}
                      {health.polling.next_full_poll_due_in_seconds_min != null
                        ? formatDurationMs(health.polling.next_full_poll_due_in_seconds_min * 1000)
                        : "--"}
                    </small>
                  </article>
                  <article className="system-health-meta-card">
                    <p>Slave Modbus TCP</p>
                    <strong>{health.modbus_tcp_slave.running ? "Online" : "Offline"}</strong>
                    <span>
                      {health.modbus_tcp_slave.host}:{health.modbus_tcp_slave.port} | ID {health.modbus_tcp_slave.unit_id}
                    </span>
                    <small>
                      {health.modbus_tcp_slave.startup_error ?? "Nessun errore di startup"}
                    </small>
                  </article>
                  <article className="system-health-meta-card">
                    <p>Storico file</p>
                    <strong>{metricFormatter.format(health.history_storage.usage_percent)}%</strong>
                    <span>occupazione storage storico</span>
                    <small>{health.history_storage.database_path}</small>
                  </article>
                </div>
              </section>

              <section className="system-health-section">
                <div className="rail-section-header">
                  <div>
                    <p className="panel-kicker">Topologia broadcast</p>
                    <h2>Gruppi comando</h2>
                  </div>
                  <span className="panel-meta">
                    {broadcastGroups.length} endpoint valutati per scrittura broadcast.
                  </span>
                </div>

                {broadcastGroups.length > 0 ? (
                  <div className="system-health-runtime-list">
                    {broadcastGroups.map((group) => {
                      const broadcastTone = buildBroadcastTone(group);
                      const previewDevices = group.devices.slice(0, 5);
                      const remainingDevices = group.devices.length - previewDevices.length;

                      return (
                        <article
                          key={`${group.endpoint_type}:${group.endpoint_label}`}
                          className={`system-health-runtime-card system-health-runtime-card--${broadcastTone}`}
                        >
                          <div className="system-health-runtime-head">
                            <div>
                              <p className="system-health-runtime-kicker">
                                {buildBroadcastTypeLabel(group)}
                                {" | "}
                                {group.device_count} device
                                {" | "}
                                {group.model_count} modelli
                              </p>
                              <strong>
                                {group.endpoint_type === "serial"
                                  ? getSerialPortDisplayName(group.endpoint_label)
                                  : group.endpoint_label}
                              </strong>
                            </div>
                            <span
                              className={`system-health-runtime-badge system-health-runtime-badge--${broadcastTone}`}
                            >
                              {buildBroadcastBadge(group)}
                            </span>
                          </div>
                          <p className="system-health-runtime-status">{group.summary}</p>
                          <p className="system-health-runtime-note">{group.detail}</p>
                          <div className="system-health-runtime-metrics">
                            <div className="system-health-runtime-metric">
                              <span>Online</span>
                              <strong>{group.online_count}/{group.device_count}</strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Profili comando</span>
                              <strong>{group.command_profile_count}</strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Broadcast</span>
                              <strong>{group.broadcast_mode}</strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Unit duplicati</span>
                              <strong>
                                {group.duplicate_unit_ids.length > 0
                                  ? group.duplicate_unit_ids.join(", ")
                                  : "nessuno"}
                              </strong>
                            </div>
                          </div>
                          {group.issues.length > 0 ? (
                            <div className="system-health-runtime-devices">
                              {group.issues.map((issue) => (
                                <span key={issue} className="system-health-chip system-health-chip--warning">
                                  {issue}
                                </span>
                              ))}
                            </div>
                          ) : null}
                          <div className="system-health-runtime-devices">
                            {previewDevices.map((device) => (
                              <span key={device.device_id} className="system-health-chip">
                                {device.name}
                                {device.unit_id !== null ? ` | unit ${device.unit_id}` : ""}
                              </span>
                            ))}
                            {remainingDevices > 0 ? (
                              <span className="system-health-chip">+{remainingDevices} altri</span>
                            ) : null}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <div className="detail-empty">
                    Nessun endpoint Modbus configurato per valutare broadcast.
                  </div>
                )}
              </section>

              <section className="system-health-section">
                <div className="rail-section-header">
                  <div>
                    <p className="panel-kicker">Endpoint di campo</p>
                    <h2>Collegamenti da seguire</h2>
                  </div>
                  <span className="panel-meta">
                    Mostra gli endpoint condivisi o quelli che richiedono una verifica.
                  </span>
                </div>

                {endpointRuntimeItems.length > 0 ? (
                  <div className="system-health-runtime-list">
                    {endpointRuntimeItems.map((runtime) => {
                      const runtimeTone = buildRuntimeTone(runtime);
                      const previewDevices = runtime.devices.slice(0, 4);
                      const remainingDevices = runtime.devices.length - previewDevices.length;

                      return (
                        <article
                          key={`${runtime.endpoint_type}:${runtime.endpoint_label}`}
                          className={`system-health-runtime-card system-health-runtime-card--${runtimeTone}`}
                        >
                          <div className="system-health-runtime-head">
                            <div>
                              <p className="system-health-runtime-kicker">
                                {buildRuntimeTypeLabel(runtime)}
                                {" | "}
                                {runtime.shared ? "condiviso" : "dedicato"}
                                {" | "}
                                {runtime.device_count} device
                              </p>
                              <strong>{buildRuntimeEndpointLabel(runtime)}</strong>
                            </div>
                            <span
                              className={`system-health-runtime-badge system-health-runtime-badge--${runtimeTone}`}
                            >
                              {buildRuntimeStateLabel(runtime)}
                            </span>
                          </div>
                          <p className="system-health-runtime-status">
                            {buildRuntimeStatusSummary(runtime)}
                          </p>
                          <p className="system-health-runtime-note">
                            {buildRuntimeNote(runtime)}
                          </p>
                          <div className="system-health-runtime-metrics">
                            <div className="system-health-runtime-metric">
                              <span>Scheduler</span>
                              <strong>{buildRuntimeSchedulerSummary(runtime)}</strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Ultimo ciclo</span>
                              <strong>{formatDurationMs(runtime.last_cycle_duration_ms)}</strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Media ciclo</span>
                              <strong>{formatDurationMs(runtime.average_cycle_duration_ms)}</strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Media operazione</span>
                              <strong>{formatDurationMs(runtime.average_operation_duration_ms)}</strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Policy comunicazione</span>
                              <strong>{runtime.adaptive_policy_mode}</strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Timeout / retry effettivi</span>
                              <strong>
                                {runtime.adaptive_timeout_seconds != null
                                  ? `${runtime.adaptive_timeout_seconds} s`
                                  : "--"}
                                {" | "}
                                {runtime.adaptive_poll_retries ?? "--"}
                              </strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Pausa tra richieste</span>
                              <strong>
                                {runtime.adaptive_inter_request_delay_ms != null
                                  ? `${runtime.adaptive_inter_request_delay_ms} ms`
                                  : "--"}
                              </strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Affidabilita recente</span>
                              <strong>
                                {runtime.recent_success_rate != null
                                  ? `${Math.round(runtime.recent_success_rate * 100)}%`
                                  : "--"}
                                {" | "}
                                {runtime.adaptive_sample_count} campioni
                              </strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Latenza richiesta P95</span>
                              <strong>{formatDurationMs(runtime.adaptive_request_p95_ms)}</strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Slave isolati</span>
                              <strong>{runtime.quarantined_device_count}</strong>
                            </div>
                            {runtime.endpoint_type === "tcp" ? (
                              <div className="system-health-runtime-metric">
                                <span>Round trip medio</span>
                                <strong>{formatDurationMs(runtime.average_round_trip_duration_ms)}</strong>
                              </div>
                            ) : null}
                            {runtime.endpoint_type === "tcp" ? (
                              <div className="system-health-runtime-metric">
                                <span>Giro potenza stimato</span>
                                <strong>
                                  {formatDurationSeconds(runtime.expected_active_power_cycle_seconds)}
                                </strong>
                              </div>
                            ) : null}
                            <div className="system-health-runtime-metric">
                              <span>SLO potenza</span>
                              <strong>{formatSloState(runtime.active_power_slo_state)}</strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Full telemetry stimata</span>
                              <strong>
                                {formatDurationSeconds(runtime.estimated_full_telemetry_cycle_seconds)}
                              </strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>SLO full telemetry</span>
                              <strong>{formatSloState(runtime.full_telemetry_slo_state)}</strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Pianificate</span>
                              <strong>
                                full {runtime.planned_full_count} | hb {runtime.planned_heartbeat_count}
                              </strong>
                            </div>
                            <div className="system-health-runtime-metric">
                              <span>Eseguite</span>
                              <strong>
                                full {runtime.executed_full_count} | hb {runtime.executed_heartbeat_count}
                              </strong>
                            </div>
                          </div>
                          {(runtime.recommendations ?? []).length > 0 ? (
                            <div className="system-health-runtime-devices">
                              {(runtime.recommendations ?? []).map((recommendation) => (
                                <span
                                  key={recommendation}
                                  className="system-health-chip system-health-chip--warning"
                                >
                                  {recommendation}
                                </span>
                              ))}
                            </div>
                          ) : null}
                          <div className="system-health-runtime-devices">
                            {previewDevices.map((deviceLabel) => (
                              <span key={deviceLabel} className="system-health-chip">
                                {deviceLabel}
                              </span>
                            ))}
                            {remainingDevices > 0 ? (
                              <span className="system-health-chip">+{remainingDevices} altri</span>
                            ) : null}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <div className="detail-empty">
                    Nessun endpoint condiviso o degradato: i collegamenti attuali risultano stabili.
                  </div>
                )}
              </section>
            </>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
