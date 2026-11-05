import { useEffect, useRef, useState } from "react";

import {
  createDevice,
  getCatalogModels,
  getDeviceOverview,
  getSerialPorts,
  getSystemOptions,
  testProtocolConnection,
  type CatalogModel,
  type Device,
  type DiscoveryCandidateProfile,
  type ProtocolTestResult,
  type SerialPortInfo,
  type SystemOptions,
} from "../api";
import { type DeviceDiscoveryPrefill } from "./DeviceDiscoveryModal";
import {
  EMPTY_PROVISION_FORM,
  PROTOCOL_DEFAULT_SETTINGS,
  PROTOCOL_TRANSPORTS,
  buildConnectionTestPayload,
  buildConnectionSettingsError,
  buildCreatePayload,
  buildProtocolSettings,
  buildSerialPortOptions,
  compareLabels,
  findCatalogEntry,
  formatConnectionSettingsText,
  formatDiagnosticValue,
  getGuidedConnectionFields,
  getGuidedFieldValue,
  isTransportAllowedForProtocol,
  listCatalogBrands,
  listCatalogModelsForBrand,
  parseConnectionSettingsSafe,
  translateDiagnosticLabel,
  translateStatusLabel,
  translateTestMessage,
  type GuidedFieldConfig,
  type ProvisionFormState,
} from "./deviceProvisioningShared";

type AddDeviceModalProps = {
  onClose: () => void;
  onCreated: () => void | Promise<void>;
  prefill: DeviceDiscoveryPrefill | null;
};

type WizardStage = "source" | "profile" | "verify" | "review" | "result";

type CommissioningOutcome = {
  monitoringState: "verified" | "pending";
  dataQualityState: "valid" | "warning" | "unknown";
  invalidPointCount: number;
  warningPointCount: number;
  note: string;
  responseTimeMs: number | null;
  lastPollStatus: string | null;
};

type StepDefinition = {
  key: WizardStage;
  title: string;
  description: string;
};

const STAGES: StepDefinition[] = [
  { key: "source", title: "Origine", description: "Nodo trovato o inserimento manuale" },
  { key: "profile", title: "Profilo", description: "Marca, modello e capability" },
  { key: "verify", title: "Verifica", description: "Parametri connessione e test" },
  { key: "review", title: "Riepilogo", description: "Controllo finale prima del salvataggio" },
  { key: "result", title: "Esito", description: "Creazione e verifica monitoraggio" },
];

const MONITORING_RETRY_COUNT = 4;
const MONITORING_RETRY_DELAY_MS = 1200;

function waitFor(milliseconds: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });
}

function buildInitialFormState(prefill: DeviceDiscoveryPrefill | null): ProvisionFormState {
  if (prefill === null) {
    return {
      ...EMPTY_PROVISION_FORM,
      connectionSettingsText: "{}",
    };
  }

  const protocol = prefill.protocol || "";
  const transport = prefill.transport || (protocol ? PROTOCOL_TRANSPORTS[protocol] ?? "" : "");
  const baseSettings =
    protocol !== ""
      ? buildProtocolSettings(protocol, prefill.connectionSettings, transport)
      : (prefill.connectionSettings ?? {});

  return {
    ...EMPTY_PROVISION_FORM,
    name: prefill.name,
    brand: prefill.brand,
    model: prefill.model,
    protocol,
    transport,
    connectionSettingsText: formatConnectionSettingsText(baseSettings),
  };
}

function describeDiscoverySignature(candidateProfileCount: number): {
  label: string;
  tone: "positive" | "neutral" | "warning";
} {
  if (candidateProfileCount <= 0) {
    return { label: "Firma non risolta", tone: "warning" };
  }
  if (candidateProfileCount === 1) {
    return { label: "Firma univoca", tone: "positive" };
  }
  return { label: "Firma di famiglia", tone: "neutral" };
}

function translateCapabilityLabel(key: keyof CatalogModel["capabilities"]): string {
  if (key === "has_active_power_limit") {
    return "Setpoint potenza attiva";
  }
  if (key === "has_reactive_power_control") {
    return "Controllo potenza reattiva";
  }
  if (key === "has_start_stop_control") {
    return "Comandi start / stop";
  }
  if (key === "supports_live_telemetry") {
    return "Telemetria live";
  }
  return "Storico potenza";
}

function humanizeSettingKey(key: string): string {
  return key
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function buildConnectionReviewEntries(
  protocol: string,
  transport: string,
  settings: Record<string, string | number | boolean>,
) {
  const guidedFields = getGuidedConnectionFields(protocol, transport);
  const entries: Array<{ label: string; value: string }> = [];
  const knownKeys = new Set<string>();

  for (const field of guidedFields) {
    knownKeys.add(field.key);
    for (const alias of field.aliases ?? []) {
      knownKeys.add(alias);
    }

    const value = getGuidedFieldValue(settings, field);
    if (value.trim().length === 0) {
      continue;
    }
    entries.push({ label: field.label, value });
  }

  for (const [key, value] of Object.entries(settings)) {
    if (knownKeys.has(key)) {
      continue;
    }
    entries.push({ label: humanizeSettingKey(key), value: String(value) });
  }

  return entries;
}

function buildSignatureText(selectedCatalogEntry: CatalogModel | null) {
  if (selectedCatalogEntry === null) {
    return "Firma di discovery disponibile dopo la selezione del modello.";
  }
  if (
    selectedCatalogEntry.discovery_signature.register == null ||
    selectedCatalogEntry.discovery_signature.function == null
  ) {
    return "Il modello non espone una firma discovery strutturata.";
  }
  return `Registro ${selectedCatalogEntry.discovery_signature.register} | funzione ${selectedCatalogEntry.discovery_signature.function}`;
}

function buildReviewBlocks(
  form: ProvisionFormState,
  selectedCatalogEntry: CatalogModel | null,
  connectionEntries: Array<{ label: string; value: string }>,
  connectionWasVerified: boolean,
  allowProceedWithoutVerifiedConnection: boolean,
) {
  return [
    {
      title: "Identita dispositivo",
      rows: [
        { label: "Nome", value: form.name || "--" },
        { label: "Marca", value: form.brand || "--" },
        { label: "Modello", value: form.model || "--" },
        { label: "Protocollo", value: form.protocol || "--" },
        { label: "Trasporto", value: form.transport || "--" },
      ],
    },
    {
      title: "Connessione",
      rows: connectionEntries.length > 0 ? connectionEntries : [{ label: "Dati", value: "--" }],
    },
    {
      title: "Commissioning",
      rows: [
        {
          label: "Connessione verificata",
          value: connectionWasVerified ? "Si" : allowProceedWithoutVerifiedConnection ? "Bypass" : "No",
        },
        {
          label: "Telemetria visibile",
          value:
            selectedCatalogEntry != null
              ? `${selectedCatalogEntry.visible_telemetry_count} punti`
              : "Da verificare",
        },
        {
          label: "Comandi scrivibili",
          value:
            selectedCatalogEntry != null
              ? `${selectedCatalogEntry.writable_command_count} comandi`
              : "Da verificare",
        },
      ],
    },
  ];
}

async function verifyCommissionedDevice(deviceId: string): Promise<CommissioningOutcome> {
  let lastPollStatus: string | null = null;

  for (let attempt = 0; attempt < MONITORING_RETRY_COUNT; attempt += 1) {
    try {
      const overview = await getDeviceOverview(deviceId);
      const telemetryCount = overview.telemetry.length;
      lastPollStatus = overview.diagnostics.last_poll_status;
      const hasConcretePolling =
        telemetryCount > 0 || lastPollStatus.toLowerCase().includes("stub_mode=false");

      if (hasConcretePolling) {
        const invalidPointCount = overview.telemetry.filter(
          (point) => point.quality === "invalid",
        ).length;
        const warningPointCount = overview.telemetry.filter(
          (point) => point.quality === "warning" || point.quality === "unavailable",
        ).length;
        const hasQualityIssues = invalidPointCount > 0 || warningPointCount > 0;
        return {
          monitoringState: "verified",
          dataQualityState: hasQualityIssues ? "warning" : "valid",
          invalidPointCount,
          warningPointCount,
          note:
            hasQualityIssues
              ? `Il dispositivo comunica, ma ${invalidPointCount} punti risultano invalidi e ${warningPointCount} richiedono verifica.`
              : telemetryCount > 0
              ? "Il dispositivo risponde e la telemetria e disponibile in dashboard."
              : "Il backend ha confermato il polling del device, ma la telemetria deve ancora stabilizzarsi.",
          responseTimeMs: overview.diagnostics.response_time_ms,
          lastPollStatus,
        };
      }
    } catch {
      lastPollStatus = null;
    }

    if (attempt < MONITORING_RETRY_COUNT - 1) {
      await waitFor(MONITORING_RETRY_DELAY_MS);
    }
  }

  return {
    monitoringState: "pending",
    dataQualityState: "unknown",
    invalidPointCount: 0,
    warningPointCount: 0,
    note:
      "Il dispositivo e stato creato correttamente, ma la verifica di monitoraggio non ha ancora restituito un ciclo valido. Controlla la dashboard tra qualche secondo.",
    responseTimeMs: null,
    lastPollStatus,
  };
}

export function AddDeviceModal({ onClose, onCreated, prefill }: AddDeviceModalProps) {
  const [catalogModels, setCatalogModels] = useState<CatalogModel[]>([]);
  const [systemOptions, setSystemOptions] = useState<SystemOptions | null>(null);
  const [serialPorts, setSerialPorts] = useState<SerialPortInfo[]>([]);
  const [loadingSetup, setLoadingSetup] = useState(true);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [form, setForm] = useState<ProvisionFormState>(() => buildInitialFormState(prefill));
  const [activeStage, setActiveStage] = useState<WizardStage>("source");
  const [testResult, setTestResult] = useState<ProtocolTestResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [testingConnection, setTestingConnection] = useState(false);
  const [creatingDevice, setCreatingDevice] = useState(false);
  const [wizardError, setWizardError] = useState<string | null>(null);
  const [allowProceedWithoutVerifiedConnection, setAllowProceedWithoutVerifiedConnection] =
    useState(false);
  const [createdDevice, setCreatedDevice] = useState<Device | null>(null);
  const [commissioningOutcome, setCommissioningOutcome] = useState<CommissioningOutcome | null>(null);
  const hasInitializedConnectionStateRef = useRef(false);

  useEffect(() => {
    let isActive = true;

    async function loadSetup() {
      setLoadingSetup(true);
      setSetupError(null);
      try {
        const [nextCatalogModels, nextSystemOptions, nextSerialPorts] = await Promise.all([
          getCatalogModels(),
          getSystemOptions(),
          getSerialPorts(),
        ]);
        if (!isActive) {
          return;
        }
        setCatalogModels(nextCatalogModels);
        setSystemOptions(nextSystemOptions);
        setSerialPorts(nextSerialPorts.ports);
      } catch (error) {
        if (!isActive) {
          return;
        }
        setSetupError(
          error instanceof Error
            ? error.message
            : "Impossibile inizializzare lo wizard di commissioning.",
        );
      } finally {
        if (isActive) {
          setLoadingSetup(false);
        }
      }
    }

    void loadSetup();

    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    setForm(buildInitialFormState(prefill));
    setActiveStage("source");
    setTestResult(null);
    setTestError(null);
    setWizardError(null);
    setAllowProceedWithoutVerifiedConnection(false);
    setCreatedDevice(null);
    setCommissioningOutcome(null);
    hasInitializedConnectionStateRef.current = false;
  }, [prefill]);

  useEffect(() => {
    if (!hasInitializedConnectionStateRef.current) {
      hasInitializedConnectionStateRef.current = true;
      return;
    }
    setTestResult(null);
    setTestError(null);
    setAllowProceedWithoutVerifiedConnection(false);
  }, [form.brand, form.model, form.protocol, form.transport, form.connectionSettingsText]);

  const sourceCandidateProfiles = prefill?.candidateProfiles ?? [];
  const discoverySignature = describeDiscoverySignature(prefill?.candidateProfileCount ?? 0);
  const catalogBrandOptions = listCatalogBrands(catalogModels, form.brand);
  const catalogModelOptions = form.brand
    ? listCatalogModelsForBrand(catalogModels, form.brand, form.model)
    : [];
  const modelProtocolOptions = Array.from(
    new Set(
      catalogModels
        .filter((catalogModel) => catalogModel.brand === form.brand && catalogModel.model === form.model)
        .map((catalogModel) => catalogModel.protocol),
    ),
  ).sort(compareLabels);
  const fallbackProtocolOptions = Array.from(
    new Set(
      [
        ...(systemOptions?.protocols ?? []),
        ...Object.keys(PROTOCOL_TRANSPORTS),
        form.protocol,
      ].filter(Boolean),
    ),
  ).sort(compareLabels);
  const protocolOptions = modelProtocolOptions.length > 0 ? modelProtocolOptions : fallbackProtocolOptions;
  const selectedCatalogEntry =
    form.brand && form.model
      ? findCatalogEntry(catalogModels, form.brand, form.model, form.protocol || undefined)
      : null;
  const parsedConnectionSettings = parseConnectionSettingsSafe(form.connectionSettingsText);
  const connectionSettingsError =
    form.protocol && form.transport
      ? buildConnectionSettingsError(form.protocol, form.transport, form.connectionSettingsText)
      : null;
  const guidedFields = getGuidedConnectionFields(form.protocol, form.transport);
  const connectionEntries =
    parsedConnectionSettings !== null
      ? buildConnectionReviewEntries(form.protocol, form.transport, parsedConnectionSettings)
      : [];
  const connectionWasVerified = testResult?.success === true;
  const reviewBlocks = buildReviewBlocks(
    form,
    selectedCatalogEntry,
    connectionEntries,
    connectionWasVerified,
    allowProceedWithoutVerifiedConnection,
  );
  const signatureText = buildSignatureText(selectedCatalogEntry);
  const sourceReady = form.name.trim().length > 0;
  const profileReady =
    form.brand.trim().length > 0 &&
    form.model.trim().length > 0 &&
    form.protocol.trim().length > 0 &&
    form.transport.trim().length > 0;
  const verifyReady = profileReady && parsedConnectionSettings !== null && connectionSettingsError === null;
  const reviewReady =
    verifyReady && (connectionWasVerified || allowProceedWithoutVerifiedConnection);
  const currentStageIndex = STAGES.findIndex((stage) => stage.key === activeStage);

  function resetWizard(usePrefill: boolean) {
    setForm(buildInitialFormState(usePrefill ? prefill : null));
    setActiveStage("source");
    setTestResult(null);
    setTestError(null);
    setWizardError(null);
    setAllowProceedWithoutVerifiedConnection(false);
    setCreatedDevice(null);
    setCommissioningOutcome(null);
  }

  function handleNameChange(value: string) {
    setForm((current) => ({ ...current, name: value }));
  }

  function handleBrandChange(value: string) {
    setForm((current) => ({
      ...current,
      brand: value,
      model: "",
      protocol: "",
      transport: "",
      connectionSettingsText: "{}",
    }));
  }

  function handleModelChange(value: string) {
    setForm((current) => {
      const selectedEntry = findCatalogEntry(catalogModels, current.brand, value, current.protocol || undefined);
      if (selectedEntry === null) {
        return { ...current, model: value };
      }

      const mergedSettings = buildProtocolSettings(
        selectedEntry.protocol,
        parseConnectionSettingsSafe(current.connectionSettingsText),
        selectedEntry.transport,
      );

      return {
        ...current,
        model: value,
        protocol: selectedEntry.protocol,
        transport: selectedEntry.transport,
        connectionSettingsText: formatConnectionSettingsText(mergedSettings),
      };
    });
  }

  function handleProtocolChange(value: string) {
    setForm((current) => {
      const exactEntry =
        current.brand && current.model
          ? catalogModels.find(
              (catalogModel) =>
                catalogModel.brand === current.brand &&
                catalogModel.model === current.model &&
                catalogModel.protocol === value,
            ) ?? null
          : null;
      const nextTransport =
        exactEntry?.transport ??
        (isTransportAllowedForProtocol(value, current.transport)
          ? current.transport
          : PROTOCOL_TRANSPORTS[value] ?? current.transport);
      const nextSettings = exactEntry
        ? { ...exactEntry.defaults }
        : buildProtocolSettings(
            value,
            parseConnectionSettingsSafe(current.connectionSettingsText),
            nextTransport,
          );

      return {
        ...current,
        protocol: value,
        transport: nextTransport,
        connectionSettingsText: formatConnectionSettingsText(nextSettings),
      };
    });
  }

  function handleConnectionSettingsTextChange(value: string) {
    setForm((current) => ({ ...current, connectionSettingsText: value }));
  }

  function handleGuidedFieldChange(field: GuidedFieldConfig, rawValue: string) {
    setForm((current) => {
      const currentSettings = buildProtocolSettings(
        current.protocol,
        parseConnectionSettingsSafe(current.connectionSettingsText),
        current.transport,
      );
      const nextSettings: Record<string, string | number | boolean> = { ...currentSettings };

      for (const alias of field.aliases ?? []) {
        delete nextSettings[alias];
      }

      if (field.type === "number") {
        if (rawValue.trim().length === 0) {
          delete nextSettings[field.key];
        } else {
          const parsedValue = Number(rawValue);
          if (Number.isFinite(parsedValue)) {
            nextSettings[field.key] = parsedValue;
          }
        }
      } else if (rawValue.trim().length === 0) {
        delete nextSettings[field.key];
      } else {
        nextSettings[field.key] = rawValue;
      }

      return {
        ...current,
        connectionSettingsText: formatConnectionSettingsText(nextSettings),
      };
    });
  }

  function applyCandidateProfile(candidate: DiscoveryCandidateProfile) {
    setForm((current) => {
      const selectedEntry = findCatalogEntry(
        catalogModels,
        candidate.brand,
        candidate.model,
        candidate.protocol,
      );
      const nextSettings = buildProtocolSettings(
        candidate.protocol,
        selectedEntry?.defaults ??
          parseConnectionSettingsSafe(current.connectionSettingsText) ??
          (prefill?.connectionSettings ?? PROTOCOL_DEFAULT_SETTINGS[candidate.protocol] ?? null),
        candidate.transport,
      );

      return {
        ...current,
        brand: candidate.brand,
        model: candidate.model,
        protocol: candidate.protocol,
        transport: candidate.transport,
        connectionSettingsText: formatConnectionSettingsText(nextSettings),
      };
    });
    setActiveStage("profile");
  }

  async function handleTestConnection() {
    setTestingConnection(true);
    setTestError(null);
    setWizardError(null);
    try {
      const result = await testProtocolConnection(buildConnectionTestPayload(form));
      setTestResult(result);
    } catch (error) {
      setTestResult(null);
      setTestError(
        error instanceof Error ? error.message : "Il test di connessione non e riuscito.",
      );
    } finally {
      setTestingConnection(false);
    }
  }

  async function handleCreateDevice() {
    setCreatingDevice(true);
    setWizardError(null);
    try {
      const device = await createDevice(buildCreatePayload(form));
      await onCreated();
      const outcome = await verifyCommissionedDevice(device.device_id);
      setCreatedDevice(device);
      setCommissioningOutcome(outcome);
      setActiveStage("result");
    } catch (error) {
      setWizardError(
        error instanceof Error
          ? error.message
          : "Impossibile completare il commissioning del dispositivo.",
      );
    } finally {
      setCreatingDevice(false);
    }
  }

  function goToNextStage() {
    if (activeStage === "source" && sourceReady) {
      setActiveStage("profile");
      return;
    }
    if (activeStage === "profile" && profileReady) {
      setActiveStage("verify");
      return;
    }
    if (activeStage === "verify" && reviewReady) {
      setActiveStage("review");
    }
  }

  function goToPreviousStage() {
    if (activeStage === "profile") {
      setActiveStage("source");
      return;
    }
    if (activeStage === "verify") {
      setActiveStage("profile");
      return;
    }
    if (activeStage === "review") {
      setActiveStage("verify");
    }
  }

  function isStageUnlocked(stage: WizardStage) {
    switch (stage) {
      case "source":
        return true;
      case "profile":
        return sourceReady || activeStage !== "source";
      case "verify":
        return profileReady || activeStage === "verify" || activeStage === "review";
      case "review":
        return reviewReady || activeStage === "review";
      case "result":
        return activeStage === "result";
      default:
        return false;
    }
  }

  const modalTitle =
    activeStage === "result" ? "Commissioning completato" : "Wizard di commissioning";
  const modalCopy =
    prefill !== null
      ? "Dal nodo trovato al dispositivo in dashboard: associa il modello, verifica la comunicazione e completa la messa in servizio."
      : "Configura un nuovo dispositivo in modo guidato, con verifica del profilo e controllo di connessione prima del salvataggio.";

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="modal-panel modal-panel--wide"
        aria-label="Wizard di commissioning dispositivo"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <div className="modal-title-group">
            <p className="panel-kicker">Provisioning guidato</p>
            <h2>{modalTitle}</h2>
            <p className="modal-copy">{modalCopy}</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose}>
            Chiudi
          </button>
        </header>

        <div className="modal-form">
          <section className="commissioning-panel">
            <div className="commissioning-panel-head">
              <div>
                <p className="panel-kicker">Percorso guidato</p>
                <h3>Stato commissioning</h3>
              </div>
              <p className="commissioning-panel-note">
                {activeStage === "result"
                  ? "Il dispositivo e stato creato. Verifica ora l'esito finale."
                  : "Ogni step sblocca il successivo e riduce gli errori di configurazione."}
              </p>
            </div>

            <div className="commissioning-steps">
              {STAGES.map((stage, index) => {
                const isCurrent = stage.key === activeStage;
                const isDone = index < currentStageIndex;
                const isWarning =
                  stage.key === "verify" &&
                  activeStage !== "result" &&
                  !connectionWasVerified &&
                  allowProceedWithoutVerifiedConnection;

                return (
                  <button
                    key={stage.key}
                    className={`commissioning-step ${
                      isDone ? "commissioning-step--done" : ""
                    } ${isCurrent ? "commissioning-step--current" : ""} ${
                      isWarning ? "commissioning-step--warning" : ""
                    }`}
                    type="button"
                    disabled={!isStageUnlocked(stage.key)}
                    onClick={() => setActiveStage(stage.key)}
                  >
                    <span className="commissioning-step-index">{index + 1}</span>
                    <span className="commissioning-step-copy">
                      <strong>{stage.title}</strong>
                      <p>{stage.description}</p>
                    </span>
                  </button>
                );
              })}
            </div>
          </section>

          {setupError ? (
            <section className="panel-state panel-state--error" role="alert">
              {setupError}
            </section>
          ) : null}

          {wizardError ? (
            <section className="panel-state panel-state--error" role="alert">
              {wizardError}
            </section>
          ) : null}

          {loadingSetup ? (
            <section className="panel-state" aria-live="polite">
              Caricamento catalogo modelli, protocolli e porte disponibili...
            </section>
          ) : null}

          {!loadingSetup && activeStage === "source" ? (
            <section className="wizard-stage-panel">
              <div className="wizard-stage-panel-head">
                <div>
                  <p className="panel-kicker">Step 1</p>
                  <h3>Origine del dispositivo</h3>
                </div>
                <span className="field-note">
                  {prefill !== null
                    ? "Nessun dato di discovery viene perso: il nodo resta precompilato."
                    : "Percorso manuale, senza nodo precompilato da discovery."}
                </span>
              </div>

              <div className="form-grid">
                <label className="field">
                  <span className="field-label">Nome dispositivo</span>
                  <input
                    className="field-control"
                    type="text"
                    value={form.name}
                    onChange={(event) => handleNameChange(event.currentTarget.value)}
                    placeholder="Es. Inverter stringa 01"
                  />
                </label>
                <label className="field">
                  <span className="field-label">Stato iniziale</span>
                  <input
                    className="field-control"
                    type="text"
                    value={translateStatusLabel(form.status)}
                    disabled
                  />
                </label>
              </div>

              {prefill !== null ? (
                <>
                  <div className="signature-strip">
                    <span
                      className={`signature-strip-badge ${
                        discoverySignature.tone === "positive"
                          ? "signature-strip-badge--positive"
                          : discoverySignature.tone === "warning"
                            ? "signature-strip-badge--warning"
                            : ""
                      }`}
                    >
                      {discoverySignature.label}
                    </span>
                    <p>
                      <strong>Nodo trovato:</strong> {prefill.sourceLabel}
                    </p>
                  </div>
                  <section className="discovery-prefill-panel">
                    <div className="discovery-prefill-header">
                      <div>
                        <p className="panel-kicker">Profili suggeriti</p>
                        <h3>Associazione iniziale del modello</h3>
                      </div>
                      <span className="discovery-prefill-count">
                        {prefill.candidateProfileCount} candidati
                      </span>
                    </div>
                    <p className="discovery-prefill-copy">
                      Se il browsing ha gia ristretto la firma, puoi partire dai profili suggeriti e poi rifinire il commissioning nello step successivo.
                    </p>
                    {sourceCandidateProfiles.length > 0 ? (
                      <div className="discovery-prefill-suggestions">
                        {sourceCandidateProfiles.map((candidate) => {
                          const isActive =
                            candidate.brand === form.brand &&
                            candidate.model === form.model &&
                            candidate.protocol === form.protocol;
                          return (
                            <button
                              key={`${candidate.brand}-${candidate.model}-${candidate.protocol}`}
                              className={`discovery-prefill-chip ${
                                isActive ? "discovery-prefill-chip--active" : ""
                              }`}
                              type="button"
                              onClick={() => applyCandidateProfile(candidate)}
                            >
                              <small>{candidate.protocol}</small>
                              <strong>{candidate.brand}</strong>
                              <span>{candidate.model}</span>
                              <span>{candidate.transport}</span>
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="discovery-prefill-empty">
                        Nessun profilo univoco disponibile. Continui dal profilo manuale nello step successivo.
                      </div>
                    )}
                  </section>
                </>
              ) : (
                <section className="signature-strip">
                  <span className="signature-strip-badge">Manuale</span>
                  <p>
                    Inserisci prima un nome chiaro, poi scegli marca e modello. Il wizard ti guidera sulla capability matrix e sui parametri di connessione.
                  </p>
                </section>
              )}
            </section>
          ) : null}

          {!loadingSetup && activeStage === "profile" ? (
            <section className="wizard-stage-panel">
              <div className="wizard-stage-panel-head">
                <div>
                  <p className="panel-kicker">Step 2</p>
                  <h3>Profilo dispositivo</h3>
                </div>
                <span className="field-note">
                  Seleziona il modello corretto: la capability matrix si aggiorna in tempo reale.
                </span>
              </div>

              <div className="form-grid">
                <label className="field">
                  <span className="field-label">Marca</span>
                  <select
                    className="field-control"
                    value={form.brand}
                    onChange={(event) => handleBrandChange(event.currentTarget.value)}
                  >
                    <option value="">Seleziona marca</option>
                    {catalogBrandOptions.map((brand) => (
                      <option key={brand} value={brand}>
                        {brand}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  <span className="field-label">Modello</span>
                  <select
                    className="field-control"
                    value={form.model}
                    onChange={(event) => handleModelChange(event.currentTarget.value)}
                    disabled={!form.brand}
                  >
                    <option value="">{form.brand ? "Seleziona modello" : "Scegli prima la marca"}</option>
                    {catalogModelOptions.map((catalogModel) => (
                      <option key={catalogModel.model} value={catalogModel.model}>
                        {catalogModel.model}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  <span className="field-label">Protocollo</span>
                  <select
                    className="field-control"
                    value={form.protocol}
                    onChange={(event) => handleProtocolChange(event.currentTarget.value)}
                    disabled={!form.model}
                  >
                    <option value="">{form.model ? "Seleziona protocollo" : "Scegli prima il modello"}</option>
                    {protocolOptions.map((protocol) => (
                      <option key={protocol} value={protocol}>
                        {protocol}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  <span className="field-label">Trasporto</span>
                  <input className="field-control" type="text" value={form.transport} disabled />
                </label>
              </div>

              {selectedCatalogEntry !== null ? (
                <>
                  <div className="signature-strip">
                    <span className="signature-strip-badge">Firma modello</span>
                    <p>{signatureText}</p>
                  </div>

                  <section className="capability-panel">
                    <div className="capability-panel-head">
                      <div>
                        <p className="panel-kicker">Capability matrix</p>
                        <h3>{selectedCatalogEntry.brand} | {selectedCatalogEntry.model}</h3>
                      </div>
                      <div className="capability-signature">
                        <strong>{selectedCatalogEntry.protocol}</strong>
                        <span>{selectedCatalogEntry.transport}</span>
                      </div>
                    </div>

                    <div className="capability-grid">
                      {Object.entries(selectedCatalogEntry.capabilities).map(([key, supported]) => (
                        <article
                          key={key}
                          className={`capability-card ${
                            supported ? "capability-card--positive" : "capability-card--warning"
                          }`}
                        >
                          <p>{translateCapabilityLabel(key as keyof CatalogModel["capabilities"])}</p>
                          <strong>{supported ? "Disponibile" : "Non esposta"}</strong>
                        </article>
                      ))}
                    </div>

                    <div className="capability-meta-grid">
                      <article className="capability-meta-card">
                        <p>Telemetria</p>
                        <strong>{selectedCatalogEntry.visible_telemetry_count}</strong>
                        <span>Punti visibili in dashboard</span>
                      </article>
                      <article className="capability-meta-card">
                        <p>Comandi</p>
                        <strong>{selectedCatalogEntry.writable_command_count}</strong>
                        <span>Comandi numerici scrivibili</span>
                      </article>
                      <article className="capability-meta-card">
                        <p>Allarmi</p>
                        <strong>{selectedCatalogEntry.alarm_count}</strong>
                        <span>Definizioni allarme mappate</span>
                      </article>
                      <article className="capability-meta-card">
                        <p>Verifica catalogo</p>
                        <strong>
                          {selectedCatalogEntry.verification.field_tested
                            ? "Collaudato in campo"
                            : selectedCatalogEntry.verification.status === "manual_verified"
                              ? "Verificato da manuale"
                              : "Da classificare"}
                        </strong>
                        <span>
                          {selectedCatalogEntry.verification.source_document ?? "Fonte non dichiarata"}
                          {selectedCatalogEntry.verification.source_version
                            ? ` | v${selectedCatalogEntry.verification.source_version}`
                            : ""}
                        </span>
                      </article>
                    </div>

                    <div className="capability-feature-list">
                      {selectedCatalogEntry.features.length > 0 ? (
                        selectedCatalogEntry.features.map((feature) => (
                          <span key={feature} className="capability-feature-chip">
                            {feature}
                          </span>
                        ))
                      ) : (
                        <span className="capability-feature-chip">Nessuna feature aggiuntiva dichiarata</span>
                      )}
                    </div>
                    {selectedCatalogEntry.verification.notes ? (
                      <p className="wizard-review-note">{selectedCatalogEntry.verification.notes}</p>
                    ) : null}
                  </section>
                </>
              ) : (
                <div className="discovery-prefill-empty">
                  Seleziona un modello supportato per mostrare firma e capability matrix.
                </div>
              )}
            </section>
          ) : null}

          {!loadingSetup && activeStage === "verify" ? (
            <section className="wizard-stage-panel">
              <div className="wizard-stage-panel-head">
                <div>
                  <p className="panel-kicker">Step 3</p>
                  <h3>Verifica connessione</h3>
                </div>
                <span className="field-note">
                  Regola i parametri della linea, testa il nodo e decidi se procedere con commissioning verificato.
                </span>
              </div>

              {form.protocol ? (
                <div className="wizard-connection-strip">
                  <strong>
                    {form.protocol} | {form.transport}
                  </strong>
                  <span>
                    {selectedCatalogEntry !== null
                      ? `${selectedCatalogEntry.brand} | ${selectedCatalogEntry.model}`
                      : "Profilo manuale"}
                  </span>
                </div>
              ) : (
                <div className="discovery-prefill-empty">
                  Seleziona prima un protocollo nello step profilo.
                </div>
              )}

              {guidedFields.length > 0 ? (
                <div className="form-grid">
                  {guidedFields.map((field) => {
                    const options =
                      form.transport === "serial" && field.key === "port"
                        ? buildSerialPortOptions(
                            serialPorts,
                            parsedConnectionSettings ? getGuidedFieldValue(parsedConnectionSettings, field) : "",
                          )
                        : field.options ?? null;

                    return (
                      <label key={field.key} className="field">
                        <span className="field-label">{field.label}</span>
                        {options ? (
                          <select
                            className="field-control"
                            value={
                              parsedConnectionSettings
                                ? getGuidedFieldValue(parsedConnectionSettings, field)
                                : ""
                            }
                            onChange={(event) =>
                              handleGuidedFieldChange(field, event.currentTarget.value)
                            }
                          >
                            <option value="">Seleziona valore</option>
                            {options.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <input
                            className="field-control"
                            type={field.type === "number" ? "number" : "text"}
                            value={
                              parsedConnectionSettings
                                ? getGuidedFieldValue(parsedConnectionSettings, field)
                                : ""
                            }
                            onChange={(event) =>
                              handleGuidedFieldChange(field, event.currentTarget.value)
                            }
                          />
                        )}
                      </label>
                    );
                  })}
                </div>
              ) : null}

              <label className="field field--full">
                <span className="field-label">Impostazioni di connessione JSON</span>
                <textarea
                  className="field-control field-control--code"
                  value={form.connectionSettingsText}
                  onChange={(event) => handleConnectionSettingsTextChange(event.currentTarget.value)}
                />
                <span className="field-note">
                  Usa il blocco guidato per i campi essenziali. Il JSON resta disponibile per retry, timeout di polling/scrittura e parametri avanzati.
                </span>
              </label>

              {connectionSettingsError ? (
                <div className="discovery-prefill-empty">{connectionSettingsError}</div>
              ) : null}

              <div className="wizard-verify-actions">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={!verifyReady || testingConnection}
                  onClick={() => void handleTestConnection()}
                >
                  {testingConnection ? "Test connessione in corso..." : "Testa connessione"}
                </button>
                <button
                  className="secondary-button secondary-button--attention"
                  type="button"
                  disabled={!verifyReady}
                  onClick={() => {
                    setAllowProceedWithoutVerifiedConnection(true);
                    setActiveStage("review");
                  }}
                >
                  Procedi senza test
                </button>
              </div>

              {testError ? (
                <section className="panel-state panel-state--error" role="alert">
                  {testError}
                </section>
              ) : null}

              {testResult ? (
                <section
                  className={`test-result ${
                    testResult.success ? "test-result--success" : "test-result--failure"
                  }`}
                >
                  <div className="test-result-header">
                    <div>
                      <p className="panel-kicker">Esito test</p>
                      <h3>{testResult.success ? "Connessione verificata" : "Connessione non confermata"}</h3>
                    </div>
                    <span
                      className={`test-badge ${
                        testResult.success ? "test-badge--success" : "test-badge--failure"
                      }`}
                    >
                      {testResult.success ? "Success" : "Errore"}
                    </span>
                  </div>
                  <p className="test-result-message">{translateTestMessage(testResult.message)}</p>
                  <div className="test-diagnostics">
                    {Object.entries(testResult.diagnostics).map(([key, value]) => (
                        <article key={key} className="test-diagnostic-card">
                          <p className="test-diagnostic-key">{translateDiagnosticLabel(key)}</p>
                          <strong className="test-diagnostic-value">
                            {formatDiagnosticValue(key, value)}
                          </strong>
                        </article>
                      ))}
                    </div>
                  </section>
              ) : null}
            </section>
          ) : null}

          {!loadingSetup && activeStage === "review" ? (
            <section className="wizard-stage-panel">
              <div className="wizard-stage-panel-head">
                <div>
                  <p className="panel-kicker">Step 4</p>
                  <h3>Riepilogo finale</h3>
                </div>
                <span className="field-note">
                  Controlla identita, endpoint e capability prima di creare il dispositivo in dashboard.
                </span>
              </div>

              <div className="wizard-review-grid">
                {reviewBlocks.map((block) => (
                  <article key={block.title} className="wizard-review-card">
                    <div className="wizard-review-block-head">
                      <strong>{block.title}</strong>
                    </div>
                    <div className="wizard-review-block">
                      {block.rows.map((row) => (
                        <div key={row.label}>
                          <span>{row.label}</span>
                          <strong>{row.value}</strong>
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>

              {selectedCatalogEntry !== null ? (
                <div className="wizard-chip-list">
                  {Object.entries(selectedCatalogEntry.capabilities).map(([key, value]) => (
                    <span
                      key={key}
                      className={`wizard-chip ${value ? "wizard-chip--positive" : "wizard-chip--warning"}`}
                    >
                      {translateCapabilityLabel(key as keyof CatalogModel["capabilities"])}
                    </span>
                  ))}
                </div>
              ) : null}

              <p className="wizard-review-note">
                {connectionWasVerified
                  ? "Il nodo ha superato il test connessione. Dopo il salvataggio il wizard verifichera anche il monitoraggio."
                  : "Stai procedendo senza un test connessione riuscito. Il dispositivo verra comunque creato e sottoposto a verifica monitoraggio."}
              </p>
            </section>
          ) : null}

          {!loadingSetup && activeStage === "result" ? (
            <section className="wizard-stage-panel">
              <div className="commissioning-result">
                <div className="commissioning-result-head">
                  <div>
                    <p className="panel-kicker">Step 5</p>
                    <h3>{createdDevice ? "Dispositivo creato" : "Commissioning non completato"}</h3>
                  </div>
                  <span
                    className={`test-badge ${
                      commissioningOutcome?.monitoringState === "verified"
                        ? "test-badge--success"
                        : "test-badge--failure"
                    }`}
                  >
                    {commissioningOutcome?.monitoringState === "verified"
                      ? "Monitoraggio ok"
                      : "Monitoraggio in attesa"}
                  </span>
                </div>

                <div className="wizard-review-grid">
                  <article className="wizard-review-card">
                    <div className="wizard-review-block-head">
                      <strong>Dispositivo</strong>
                    </div>
                    <div className="wizard-review-block">
                      <div>
                        <span>Nome</span>
                        <strong>{createdDevice?.name ?? "--"}</strong>
                      </div>
                      <div>
                        <span>Marca / modello</span>
                        <strong>
                          {createdDevice ? `${createdDevice.brand} | ${createdDevice.model}` : "--"}
                        </strong>
                      </div>
                      <div>
                        <span>Protocollo</span>
                        <strong>
                          {createdDevice ? `${createdDevice.protocol} | ${createdDevice.transport}` : "--"}
                        </strong>
                      </div>
                    </div>
                  </article>

                  <article className="wizard-review-card">
                    <div className="wizard-review-block-head">
                      <strong>Verifica monitoraggio</strong>
                    </div>
                    <div className="wizard-review-block">
                      <div>
                        <span>Esito</span>
                        <strong>
                          {commissioningOutcome?.monitoringState === "verified"
                            ? "Telemetria confermata"
                            : "Da confermare"}
                        </strong>
                      </div>
                      <div>
                        <span>Tempo risposta</span>
                        <strong>
                          {commissioningOutcome?.responseTimeMs != null
                            ? `${commissioningOutcome.responseTimeMs} ms`
                            : "--"}
                        </strong>
                      </div>
                      <div>
                        <span>Ultimo polling</span>
                        <strong>{commissioningOutcome?.lastPollStatus ?? "--"}</strong>
                      </div>
                      <div>
                        <span>Qualita dati</span>
                        <strong>
                          {commissioningOutcome?.dataQualityState === "valid"
                            ? "Valori plausibili"
                            : commissioningOutcome?.dataQualityState === "warning"
                              ? `${commissioningOutcome.invalidPointCount} invalidi | ${commissioningOutcome.warningPointCount} da verificare`
                              : "Da misurare"}
                        </strong>
                      </div>
                    </div>
                  </article>
                </div>

                <p className="wizard-review-note">
                  {commissioningOutcome?.note ??
                    "Il wizard ha terminato la creazione del dispositivo."}
                </p>
              </div>
            </section>
          ) : null}

          <footer className="modal-footer">
            {activeStage === "source" ? (
              <>
                <button className="secondary-button" type="button" onClick={onClose}>
                  Annulla
                </button>
                <button
                  className="action-button"
                  type="button"
                  disabled={!sourceReady || loadingSetup}
                  onClick={goToNextStage}
                >
                  Continua al profilo
                </button>
              </>
            ) : null}

            {activeStage === "profile" ? (
              <>
                <button className="secondary-button" type="button" onClick={goToPreviousStage}>
                  Torna all'origine
                </button>
                <button
                  className="action-button"
                  type="button"
                  disabled={!profileReady}
                  onClick={goToNextStage}
                >
                  Continua alla verifica
                </button>
              </>
            ) : null}

            {activeStage === "verify" ? (
              <>
                <button className="secondary-button" type="button" onClick={goToPreviousStage}>
                  Torna al profilo
                </button>
                <button
                  className="action-button"
                  type="button"
                  disabled={!reviewReady}
                  onClick={goToNextStage}
                >
                  Continua al riepilogo
                </button>
              </>
            ) : null}

            {activeStage === "review" ? (
              <>
                <button className="secondary-button" type="button" onClick={goToPreviousStage}>
                  Torna alla verifica
                </button>
                <button
                  className="action-button"
                  type="button"
                  disabled={creatingDevice}
                  onClick={() => void handleCreateDevice()}
                >
                  {creatingDevice ? "Commissioning in corso..." : "Completa commissioning"}
                </button>
              </>
            ) : null}

            {activeStage === "result" ? (
              <>
                <button className="secondary-button" type="button" onClick={onClose}>
                  Chiudi wizard
                </button>
                <button
                  className="action-button"
                  type="button"
                  onClick={() => resetWizard(false)}
                >
                  Configura un altro dispositivo
                </button>
              </>
            ) : null}
          </footer>
        </div>
      </aside>
    </div>
  );
}
