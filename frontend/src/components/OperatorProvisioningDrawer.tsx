import { useEffect, useMemo, useRef, useState } from "react";

import {
  createDevice,
  cancelProtocolOperation,
  discoverRtuDevices,
  discoverTcpDevices,
  finishProtocolOperation,
  getCatalogModels,
  getNetworkInterfaces,
  getProtocolOperationState,
  getSerialPorts,
  testProtocolConnection,
  type CatalogModel,
  type ConnectionSettings,
  type Device,
  type DeviceDiscoveryRtuResult,
  type DeviceDiscoveryTcpResult,
  type NetworkInterfaceInfo,
  type ProtocolOperationState,
  type ProtocolTestResult,
  type RtuDiscoveryProtocol,
  type SerialPortInfo,
} from "../api";
import {
  buildProtocolSettings,
  buildSerialPortOptions,
  compareLabels,
  getSerialPortDisplayName,
  listCatalogBrands,
  listCatalogModelsForBrand,
  normalizeConnectionSettings,
  translateTestMessage,
} from "./deviceProvisioningShared";
import { getSettingsAccentClass, SETTINGS_SECTION_CONTENT } from "../settingsSections";

type ProvisioningLinkMode = "serial" | "tcp" | "gateway_ip";
type GatewayProtocolMode = "rtu_over_tcp" | "tcp";

type OperatorProvisioningDrawerProps = {
  open: boolean;
  existingDevices: Device[];
  cancelRequestToken?: number;
  onClose: () => void;
  onCreated: (createdDevices: Device[]) => void | Promise<void>;
  onBusyChange?: (busy: boolean) => void;
  onProgressChange?: (progress: OperatorProvisioningProgressState | null) => void;
  onScanBusyChange?: (busy: boolean) => void;
  onScanResultCountChange?: (count: number) => void;
};

type SerialScanForm = {
  port: string;
  baudRate: string;
  parity: string;
  stopBits: string;
  byteSize: string;
  timeoutSeconds: string;
  retries: string;
  slaveIdStart: string;
  slaveIdEnd: string;
  scanProtocol: RtuDiscoveryProtocol;
};

type NetworkScanForm = {
  interfaceAddress: string;
  hostStart: string;
  hostEnd: string;
  portStart: string;
  portEnd: string;
  timeoutSeconds: string;
  retries: string;
  unitIdStart: string;
  unitIdEnd: string;
};

type SelectedEndpoint = {
  key: string;
  label: string;
  protocol: string;
  transport: string;
  transportLabel: string;
  connectionSettings: ConnectionSettings;
  existingDevice: Device | null;
  discoveredVia: ProvisioningLinkMode;
  compatibility:
    | "matched_signature"
    | "candidate_signature"
    | "manual_selection"
    | "unverified_signature";
};

type DecoratedResult = {
  key: string;
  label: string;
  description: string;
  candidateSummary: string;
  candidateDetails: string[];
  compatibility:
    | "matched_signature"
    | "candidate_signature"
    | "manual_selection"
    | "unverified_signature";
  existingDevice: Device | null;
  buildEndpoint: () => SelectedEndpoint;
};

type SelectedCreationPlan = {
  key: string;
  endpoint: SelectedEndpoint;
  plannedName: string;
};

export type OperatorProvisioningProgressItem = {
  key: string;
  name: string;
  endpointLabel: string;
  status: "pending" | "running" | "success" | "error";
  message: string;
};

export type OperatorProvisioningProgressState = {
  total: number;
  completed: number;
  currentName: string | null;
  items: OperatorProvisioningProgressItem[];
};

export type OperatorProvisioningScanProgressState = {
  mode: "serial" | "tcp" | "gateway_ip";
  total: number;
  completed: number;
  found: number;
  currentLabel: string | null;
  status: "running" | "success" | "warning" | "error";
  message: string;
};

type CreationProgressState = OperatorProvisioningProgressState;

const SERIAL_DEFAULTS: SerialScanForm = {
  port: "",
  baudRate: "9600",
  parity: "N",
  stopBits: "1",
  byteSize: "8",
  timeoutSeconds: "0.35",
  retries: "0",
  slaveIdStart: "1",
  slaveIdEnd: "32",
  scanProtocol: "modbus_rtu",
};

const NETWORK_DEFAULTS: NetworkScanForm = {
  interfaceAddress: "",
  hostStart: "",
  hostEnd: "",
  portStart: "502",
  portEnd: "502",
  timeoutSeconds: "0.35",
  retries: "0",
  unitIdStart: "1",
  unitIdEnd: "4",
};

const PARITY_OPTIONS = ["N", "E", "O"];
// Keep RTU discovery windows smaller than the backend hard limit to reduce
// timeouts and bus saturation on real RS485 lines.
const RTU_DISCOVERY_MAX_SLAVE_IDS_PER_REQUEST = 16;
const TCP_DISCOVERY_MAX_UNIT_IDS_PER_REQUEST = 16;

function createProtocolOperationId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `op-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function describeProtocolOperation(state: ProtocolOperationState | null): string | null {
  if (!state?.active) {
    return null;
  }
  const label = state.label || state.kind || "operazione protocollo";
  const connections = state.active_connections === 1 ? "1 connessione" : `${state.active_connections} connessioni`;
  return state.cancel_requested
    ? `${label}: arresto in corso, ${connections} aperte.`
    : `${label}: ${connections} aperte.`;
}

function buildIntegerRange(startRaw: string, endRaw: string, min: number, max: number): number[] {
  const startValue = Number(startRaw);
  const endValue = Number(endRaw);
  if (!Number.isInteger(startValue) || !Number.isInteger(endValue)) {
    throw new Error("Inserisci un intervallo numerico valido.");
  }
  if (startValue < min || endValue > max || startValue > endValue) {
    throw new Error(`L'intervallo deve restare tra ${min} e ${max}.`);
  }
  return Array.from({ length: endValue - startValue + 1 }, (_, index) => startValue + index);
}

function parseIpv4Address(address: string): number[] {
  const parts = address
    .trim()
    .split(".")
    .map((part) => Number(part));
  if (
    parts.length !== 4 ||
    parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)
  ) {
    throw new Error("Inserisci un intervallo IP valido.");
  }
  return parts;
}

function buildIpv4HostRange(startRaw: string, endRaw: string): string[] {
  const startParts = parseIpv4Address(startRaw);
  const endParts = parseIpv4Address(endRaw);
  if (
    startParts[0] !== endParts[0] ||
    startParts[1] !== endParts[1] ||
    startParts[2] !== endParts[2]
  ) {
    throw new Error("La scansione TCP deve restare nella stessa subnet /24.");
  }
  if (startParts[3] > endParts[3]) {
    throw new Error("L'intervallo IP iniziale deve precedere quello finale.");
  }
  return Array.from(
    { length: endParts[3] - startParts[3] + 1 },
    (_, index) => `${startParts[0]}.${startParts[1]}.${startParts[2]}.${startParts[3] + index}`,
  );
}

function chunkItems<T>(items: T[], chunkSize: number): T[][] {
  if (chunkSize <= 0) {
    return [items];
  }
  const chunks: T[][] = [];
  for (let index = 0; index < items.length; index += chunkSize) {
    chunks.push(items.slice(index, index + chunkSize));
  }
  return chunks;
}

function buildHostSelectionRange(address: string): { start: string; end: string } | null {
  if (!address || address === "0.0.0.0") {
    return null;
  }
  return { start: address, end: address };
}

function pickDefaultInterface(interfaces: NetworkInterfaceInfo[]): NetworkInterfaceInfo | null {
  return (
    interfaces.find(
      (networkInterface) =>
        networkInterface.address !== "0.0.0.0" && networkInterface.address !== "127.0.0.1",
    ) ??
    interfaces[0] ??
    null
  );
}

function findNumericConnectionValue(
  settings: ConnectionSettings,
  key: string,
  aliases: string[] = [],
): number | null {
  for (const candidateKey of [key, ...aliases]) {
    const value = settings[candidateKey];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === "string" && value.trim() !== "") {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }
  return null;
}

function findStringConnectionValue(
  settings: ConnectionSettings,
  key: string,
  aliases: string[] = [],
): string | null {
  for (const candidateKey of [key, ...aliases]) {
    const value = settings[candidateKey];
    if (typeof value === "string" && value.trim() !== "") {
      return value.trim();
    }
  }
  return null;
}

function matchExistingSerialDevice(
  result: DeviceDiscoveryRtuResult,
  devices: Device[],
): Device | null {
  return (
    devices.find((device) => {
      if (device.transport !== "serial") {
        return false;
      }
      const port = findStringConnectionValue(device.connection_settings, "port");
      const unitId = findNumericConnectionValue(device.connection_settings, "slave_id", [
        "address",
        "unit_id",
      ]);
      return port === result.port && unitId === result.unit_id;
    }) ?? null
  );
}

function matchExistingTcpDevice(
  result: DeviceDiscoveryTcpResult,
  devices: Device[],
): Device | null {
  return (
    devices.find((device) => {
      if (device.transport !== "tcp") {
        return false;
      }
      const host = findStringConnectionValue(device.connection_settings, "host");
      const port = findNumericConnectionValue(device.connection_settings, "port");
      const unitId = findNumericConnectionValue(device.connection_settings, "unit_id", [
        "slave_id",
      ]);
      return host === result.host && port === result.port && unitId === result.unit_id;
    }) ?? null
  );
}

function describeCompatibility(
  resultCandidates: Array<{ brand: string; model: string; protocol: string; transport: string }>,
  selectedCatalogEntry: CatalogModel | null,
): DecoratedResult["compatibility"] {
  if (selectedCatalogEntry === null) {
    return "manual_selection";
  }
  if (resultCandidates.length === 0) {
    return "unverified_signature";
  }
  const exactMatch = resultCandidates.some(
    (candidate) =>
      candidate.brand === selectedCatalogEntry.brand &&
      candidate.model === selectedCatalogEntry.model &&
      candidate.protocol === selectedCatalogEntry.protocol &&
      candidate.transport === selectedCatalogEntry.transport,
  );
  if (exactMatch) {
    return "matched_signature";
  }
  const brandMatch = resultCandidates.some((candidate) => candidate.brand === selectedCatalogEntry.brand);
  return brandMatch ? "candidate_signature" : "manual_selection";
}

function buildCompatibilityLabel(
  compatibility: DecoratedResult["compatibility"],
): { label: string; tone: "positive" | "neutral" | "warning" } {
  switch (compatibility) {
    case "matched_signature":
      return { label: "Firma coerente", tone: "positive" };
    case "candidate_signature":
      return { label: "Firma compatibile", tone: "neutral" };
    case "unverified_signature":
      return { label: "Firma assente", tone: "warning" };
    default:
      return { label: "Selezione manuale", tone: "warning" };
  }
}

function buildScanCandidateSummary(
  count: number,
  details: string[],
): { headline: string; detailLines: string[] } {
  if (count <= 0) {
    return {
      headline: "Nodo trovato, profilo da verificare",
      detailLines: ["La firma discovery non ha riconosciuto un modello univoco."],
    };
  }
  if (count === 1 && details.length > 0) {
    return {
      headline: "Profilo univoco rilevato",
      detailLines: [details[0]],
    };
  }
  return {
    headline: `${count} profili compatibili`,
    detailLines: details.slice(0, 3),
  };
}

function buildSuggestedName(
  model: string,
  fallbackPrefix: string,
  identifier: string | number,
): string {
  const normalizedModel = model.trim();
  if (normalizedModel.length > 0) {
    return `${normalizedModel} ${identifier}`;
  }
  return `${fallbackPrefix} ${identifier}`;
}

function buildPlannedDeviceNames(baseName: string, count: number, existingDevices: Device[]): string[] {
  const trimmedBaseName = baseName.trim();
  if (!trimmedBaseName || count <= 0) {
    return [];
  }

  const usedNames = new Set(
    existingDevices
      .map((device) => device.name.trim().toLowerCase())
      .filter((value) => value.length > 0),
  );

  return Array.from({ length: count }, (_, index) => {
    let suffix = index === 0 ? null : index + 1;
    let candidate = suffix === null ? trimmedBaseName : `${trimmedBaseName}_${suffix}`;
    while (usedNames.has(candidate.toLowerCase())) {
      suffix = suffix === null ? 2 : suffix + 1;
      candidate = `${trimmedBaseName}_${suffix}`;
    }
    usedNames.add(candidate.toLowerCase());
    return candidate;
  });
}

function buildSerialConnectionSettings(
  protocol: string,
  defaults: ConnectionSettings,
  result: DeviceDiscoveryRtuResult,
  form: SerialScanForm,
): ConnectionSettings {
  const nextSettings: ConnectionSettings = {
    ...buildProtocolSettings(protocol, defaults, "serial"),
    port: result.port,
    baud_rate: Number(form.baudRate),
    parity: form.parity,
    stop_bits: Number(form.stopBits),
    byte_size: Number(form.byteSize),
    timeout_seconds: Number(form.timeoutSeconds),
    retries: Number(form.retries),
  };
  if (protocol === "aurora" || protocol === "delta_rs485") {
    nextSettings.address = result.unit_id;
  } else {
    nextSettings.slave_id = result.unit_id;
  }
  return nextSettings;
}

function buildTcpConnectionSettings(
  protocol: string,
  transport: string,
  defaults: ConnectionSettings,
  result: DeviceDiscoveryTcpResult,
  form: NetworkScanForm,
): ConnectionSettings {
  return {
    ...buildProtocolSettings(protocol, defaults, transport),
    host: result.host,
    port: result.port,
    unit_id: result.unit_id,
    timeout_seconds: Number(form.timeoutSeconds),
    retries: Number(form.retries),
  };
}

function buildEndpointTroubleshootingContext(endpoint: SelectedEndpoint): string {
  if (endpoint.discoveredVia === "serial") {
    const port = findStringConnectionValue(endpoint.connectionSettings, "port") ?? "--";
    const displayPort = getSerialPortDisplayName(port);
    const slaveId =
      findNumericConnectionValue(endpoint.connectionSettings, "slave_id", ["address"]) ?? "--";
    const baudRate = findNumericConnectionValue(endpoint.connectionSettings, "baud_rate") ?? "--";
    const parity = findStringConnectionValue(endpoint.connectionSettings, "parity") ?? "--";
    const stopBits = findNumericConnectionValue(endpoint.connectionSettings, "stop_bits") ?? "--";
    return `Linea ${displayPort} | slave ${slaveId} | ${baudRate} baud | parity ${parity} | stop ${stopBits}.`;
  }

  const host = findStringConnectionValue(endpoint.connectionSettings, "host") ?? "--";
  const port = findNumericConnectionValue(endpoint.connectionSettings, "port") ?? "--";
  const unitId = findNumericConnectionValue(endpoint.connectionSettings, "unit_id", ["slave_id"]) ?? "--";
  return `Endpoint ${host}:${port} | unit ${unitId}.`;
}

function buildProvisioningRecoveryHint(
  transport: string,
  endpoint: SelectedEndpoint,
  stage: string | null,
): string {
  if (stage === "settings") {
    return `Controlla i parametri di connessione del profilo selezionato. ${buildEndpointTroubleshootingContext(endpoint)}`;
  }

  if (stage === "profile" || stage === "transport") {
    return "Verifica marca, modello e protocollo: il nodo trovato potrebbe non corrispondere al profilo scelto.";
  }

  if (transport === "serial") {
    return `Verifica porta, baud rate, parita, bit di stop, cablaggio RS485 e terminazione. ${buildEndpointTroubleshootingContext(endpoint)}`;
  }

  return `Verifica IP, porta TCP, unit ID e subnet dell'inverter o del gateway. ${buildEndpointTroubleshootingContext(endpoint)}`;
}

function buildProvisioningTestErrorMessage(
  result: ProtocolTestResult,
  endpoint: SelectedEndpoint,
  transport: string,
): string {
  const translatedMessage = translateTestMessage(result.message);
  const stage = typeof result.diagnostics.stage === "string" ? result.diagnostics.stage : null;
  return `${translatedMessage} ${buildProvisioningRecoveryHint(transport, endpoint, stage)}`.trim();
}

function buildProvisioningRuntimeErrorMessage(
  error: unknown,
  endpoint: SelectedEndpoint,
  transport: string,
): string {
  const baseMessage =
    error instanceof Error ? error.message : "Operazione non riuscita durante la configurazione.";
  const normalizedMessage = baseMessage.toLowerCase();
  const stage = normalizedMessage.includes("protocollo")
    ? "profile"
    : normalizedMessage.includes("parametri")
      ? "settings"
      : normalizedMessage.includes("trasporto")
        ? "transport"
        : null;
  return `${baseMessage} ${buildProvisioningRecoveryHint(transport, endpoint, stage)}`.trim();
}

function OperatorScanProgressPanel({
  progress,
  busy,
  onCancel,
  onDismiss,
}: {
  progress: OperatorProvisioningScanProgressState;
  busy: boolean;
  onCancel?: () => void;
  onDismiss: () => void;
}) {
  const progressPercent =
    progress.total > 0 ? Math.round((progress.completed / progress.total) * 100) : 0;
  const hasError = progress.status === "error";
  const hasWarning = progress.status === "warning";
  const modeLabel =
    progress.mode === "serial"
      ? "RS485"
      : progress.mode === "gateway_ip"
        ? "Gateway IP"
        : "TCP";
  const headline = busy
    ? progress.currentLabel
      ? `Scansione in corso: ${progress.currentLabel}`
      : `Scansione ${modeLabel} in corso`
    : hasError
      ? "Scansione completata con errori"
      : hasWarning
        ? "Scansione completata con avvisi"
        : "Scansione completata";

  return (
    <section
      className={`operator-provision-progress operator-provision-progress--scan ${
        hasError ? "operator-provision-progress--error" : ""
      } ${hasWarning ? "operator-provision-progress--warning" : ""}`}
      role={hasError ? "alert" : "status"}
    >
      <div className="operator-provision-progress__head">
        <div>
          <p className="panel-kicker">Scanning {modeLabel}</p>
          <strong>{headline}</strong>
          <p className="operator-provision-progress__caption">{progress.message}</p>
        </div>
        <div className="operator-provision-progress__actions">
          <span>{progressPercent}%</span>
          {busy && onCancel ? (
            <button className="chip-inline-button" type="button" onClick={onCancel}>
              Interrompi
            </button>
          ) : null}
          {!busy ? (
            <button className="chip-inline-button" type="button" onClick={onDismiss}>
              Chiudi
            </button>
          ) : null}
        </div>
      </div>
      <div className="operator-provision-progress__track" aria-hidden="true">
        <span style={{ width: `${Math.max(4, progressPercent)}%` }} />
      </div>
      <div className="operator-provision-progress__summary">
        <span>
          {progress.completed}/{progress.total} controllati
        </span>
        <span>{progress.found} nodi trovati</span>
        {progress.currentLabel ? <span>In scansione: {progress.currentLabel}</span> : null}
      </div>
    </section>
  );
}

export function OperatorProvisioningDrawer({
  open,
  existingDevices,
  cancelRequestToken = 0,
  onClose,
  onCreated,
  onBusyChange,
  onProgressChange,
  onScanBusyChange,
  onScanResultCountChange,
}: OperatorProvisioningDrawerProps) {
  const cancelRequestedRef = useRef(false);
  const scanAbortControllerRef = useRef<AbortController | null>(null);
  const activeScanOperationIdRef = useRef<string | null>(null);
  const lastCancelRequestTokenRef = useRef(cancelRequestToken);
  const [catalogModels, setCatalogModels] = useState<CatalogModel[]>([]);
  const [serialPorts, setSerialPorts] = useState<SerialPortInfo[]>([]);
  const [networkInterfaces, setNetworkInterfaces] = useState<NetworkInterfaceInfo[]>([]);
  const [loadingSetup, setLoadingSetup] = useState(false);
  const [setupError, setSetupError] = useState<string | null>(null);

  const [deviceName, setDeviceName] = useState("");
  const [linkMode, setLinkMode] = useState<ProvisioningLinkMode>("serial");
  const [gatewayProtocolMode, setGatewayProtocolMode] = useState<GatewayProtocolMode>("rtu_over_tcp");
  const [brand, setBrand] = useState("");
  const [model, setModel] = useState("");
  const [protocol, setProtocol] = useState("");

  const [serialForm, setSerialForm] = useState<SerialScanForm>(SERIAL_DEFAULTS);
  const [networkForm, setNetworkForm] = useState<NetworkScanForm>(NETWORK_DEFAULTS);

  const [serialResults, setSerialResults] = useState<DeviceDiscoveryRtuResult[]>([]);
  const [tcpResults, setTcpResults] = useState<DeviceDiscoveryTcpResult[]>([]);
  const [scanBusy, setScanBusy] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanInfo, setScanInfo] = useState<string | null>(null);
  const [protocolOperationState, setProtocolOperationState] = useState<ProtocolOperationState | null>(null);

  const [focusedEndpointKey, setFocusedEndpointKey] = useState<string | null>(null);
  const [selectedEndpointKeys, setSelectedEndpointKeys] = useState<string[]>([]);

  const [testingConnection, setTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState<ProtocolTestResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const [creatingDevice, setCreatingDevice] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);
  const [creationProgress, setCreationProgress] = useState<CreationProgressState | null>(null);
  const [scanProgress, setScanProgress] = useState<OperatorProvisioningScanProgressState | null>(null);
  const scanResultCount = serialResults.length + tcpResults.length;

  const gatewayUsesRtuOverTcp = linkMode === "gateway_ip" && gatewayProtocolMode === "rtu_over_tcp";
  const catalogTransport = linkMode === "serial" || gatewayUsesRtuOverTcp ? "serial" : "tcp";
  const scanTransport = linkMode === "serial" ? "serial" : "tcp";
  const compatibleCatalog = useMemo(
    () =>
      catalogModels.filter(
        (catalogModel) =>
          catalogModel.transport === catalogTransport &&
          (!gatewayUsesRtuOverTcp || catalogModel.protocol === "modbus_rtu"),
      ),
    [catalogModels, catalogTransport, gatewayUsesRtuOverTcp],
  );

  const brandOptions = useMemo(
    () => listCatalogBrands(compatibleCatalog, brand),
    [brand, compatibleCatalog],
  );
  const modelOptions = useMemo(
    () => (brand ? listCatalogModelsForBrand(compatibleCatalog, brand, model) : []),
    [brand, compatibleCatalog, model],
  );
  const modelEntries = useMemo(
    () =>
      brand && model
        ? compatibleCatalog
            .filter((catalogModel) => catalogModel.brand === brand && catalogModel.model === model)
            .sort((left, right) => compareLabels(left.protocol, right.protocol))
        : [],
    [brand, compatibleCatalog, model],
  );
  const protocolOptions = useMemo(
    () => modelEntries.map((catalogModel) => catalogModel.protocol),
    [modelEntries],
  );
  const selectedCatalogEntry = useMemo(
    () =>
      protocol
        ? compatibleCatalog.find(
            (catalogModel) =>
              catalogModel.brand === brand &&
              catalogModel.model === model &&
              catalogModel.protocol === protocol,
          ) ?? null
        : modelEntries.length === 1
          ? modelEntries[0]
          : null,
    [brand, compatibleCatalog, model, modelEntries, protocol],
  );

  const serialPortOptions = useMemo(
    () => buildSerialPortOptions(serialPorts, serialForm.port),
    [serialForm.port, serialPorts],
  );
  const networkInterfaceOptions = useMemo(
    () =>
      networkInterfaces.map((networkInterface) => ({
        value: networkInterface.address,
        label: `${networkInterface.name} | ${networkInterface.address}`,
      })),
    [networkInterfaces],
  );

  useEffect(() => {
    if (!open || creatingDevice) {
      return;
    }
    cancelRequestedRef.current = false;
    setDeviceName("");
    setLinkMode("serial");
    setGatewayProtocolMode("rtu_over_tcp");
    setBrand("");
    setModel("");
    setProtocol("");
    setSerialForm(SERIAL_DEFAULTS);
    setNetworkForm(NETWORK_DEFAULTS);
    setSerialResults([]);
    setTcpResults([]);
    setScanBusy(false);
    setScanError(null);
    setScanInfo(null);
    setProtocolOperationState(null);
    setScanProgress(null);
    setFocusedEndpointKey(null);
    setSelectedEndpointKeys([]);
    setTestResult(null);
    setTestError(null);
    setCreatingDevice(false);
    setCreateError(null);
    setCreateSuccess(null);
    setCreationProgress(null);
  }, [creatingDevice, open]);

  useEffect(() => {
    onBusyChange?.(creatingDevice);
  }, [creatingDevice, onBusyChange]);

  useEffect(() => {
    onProgressChange?.(creationProgress);
  }, [creationProgress, onProgressChange]);

  useEffect(() => {
    onScanBusyChange?.(scanBusy || protocolOperationState?.active === true);
  }, [onScanBusyChange, protocolOperationState?.active, scanBusy]);

  useEffect(() => {
    if (open) {
      return;
    }
    const operationId = activeScanOperationIdRef.current;
    if (operationId) {
      void cancelProtocolOperation({
        operation_id: operationId,
        reason: "drawer_closed",
      }).catch(() => undefined);
      activeScanOperationIdRef.current = null;
    }
    scanAbortControllerRef.current?.abort();
    scanAbortControllerRef.current = null;
  }, [open]);

  useEffect(
    () => () => {
      const operationId = activeScanOperationIdRef.current;
      if (operationId) {
        void cancelProtocolOperation({
          operation_id: operationId,
          reason: "drawer_unmounted",
        }).catch(() => undefined);
        activeScanOperationIdRef.current = null;
      }
      scanAbortControllerRef.current?.abort();
      scanAbortControllerRef.current = null;
    },
    [],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    let isActive = true;

    async function refreshOperationState() {
      try {
        const state = await getProtocolOperationState();
        if (!isActive) {
          return;
        }
        setProtocolOperationState(state);
      } catch {
        if (isActive) {
          setProtocolOperationState(null);
        }
      }
    }

    void refreshOperationState();
    const intervalId = window.setInterval(refreshOperationState, scanBusy ? 1000 : 2500);
    return () => {
      isActive = false;
      window.clearInterval(intervalId);
    };
  }, [open, scanBusy]);

  useEffect(() => {
    if (open || scanBusy || scanResultCount > 0) {
      onScanResultCountChange?.(scanResultCount);
    }
  }, [onScanResultCountChange, open, scanBusy, scanResultCount]);

  useEffect(() => {
    if (cancelRequestToken === lastCancelRequestTokenRef.current) {
      return;
    }
    lastCancelRequestTokenRef.current = cancelRequestToken;
    if (!creatingDevice) {
      return;
    }
    cancelRequestedRef.current = true;
    setCreateError("Blocco richiesto: termino il dispositivo in corso e salto quelli ancora in coda.");
    setCreationProgress((current) =>
      current
        ? {
            ...current,
            items: current.items.map((item) =>
              item.status === "pending"
                ? { ...item, message: "In attesa di blocco" }
                : item.status === "running"
                  ? { ...item, message: "Blocco richiesto" }
                  : item,
            ),
          }
        : current,
    );
  }, [cancelRequestToken, creatingDevice]);

  useEffect(() => {
    if (!open) {
      return;
    }

    let isActive = true;

    async function loadSetup() {
      setLoadingSetup(true);
      setSetupError(null);
      try {
        const [nextCatalogModels, nextSerialPorts, nextNetworkInterfaces] = await Promise.all([
          getCatalogModels(),
          getSerialPorts(),
          getNetworkInterfaces(),
        ]);
        if (!isActive) {
          return;
        }
        const defaultPort = nextSerialPorts.ports[0]?.name ?? "";
        const defaultInterface = pickDefaultInterface(nextNetworkInterfaces.interfaces);
        const defaultRange = defaultInterface ? buildHostSelectionRange(defaultInterface.address) : null;

        setCatalogModels(nextCatalogModels);
        setSerialPorts(nextSerialPorts.ports);
        setNetworkInterfaces(nextNetworkInterfaces.interfaces);
        setSerialForm((current) => ({
          ...current,
          port: current.port || defaultPort,
        }));
        setNetworkForm((current) => ({
          ...current,
          interfaceAddress: current.interfaceAddress || defaultInterface?.address || "",
          hostStart: current.hostStart || defaultRange?.start || "",
          hostEnd: current.hostEnd || defaultRange?.end || "",
        }));
      } catch (error) {
        if (!isActive) {
          return;
        }
        setSetupError(
          error instanceof Error
            ? error.message
            : "Impossibile caricare il catalogo e le opzioni di configurazione.",
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
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    setScanError(null);
    setScanInfo(null);
    setScanProgress(null);
    setFocusedEndpointKey(null);
    setSelectedEndpointKeys([]);
    setTestResult(null);
    setTestError(null);
    setCreateError(null);
    setCreateSuccess(null);
    setCreationProgress(null);
  }, [brand, gatewayProtocolMode, linkMode, model, open, protocol]);

  useEffect(() => {
    if (!open) {
      return;
    }
    if (brand && !compatibleCatalog.some((catalogModel) => catalogModel.brand === brand)) {
      setBrand("");
      setModel("");
      setProtocol("");
      return;
    }
    if (
      brand &&
      model &&
      !compatibleCatalog.some(
        (catalogModel) => catalogModel.brand === brand && catalogModel.model === model,
      )
    ) {
      setModel("");
      setProtocol("");
    }
  }, [brand, compatibleCatalog, model, open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    if (modelEntries.length === 1) {
      if (protocol !== modelEntries[0].protocol) {
        setProtocol(modelEntries[0].protocol);
      }
      return;
    }
    if (protocol && !modelEntries.some((catalogModel) => catalogModel.protocol === protocol)) {
      setProtocol("");
    }
  }, [modelEntries, open, protocol]);

  useEffect(() => {
    if (!open || scanTransport !== "serial" || selectedCatalogEntry === null) {
      return;
    }
    const defaults = buildProtocolSettings(selectedCatalogEntry.protocol, selectedCatalogEntry.defaults);
    setSerialForm((current) => ({
      ...current,
      baudRate: String(defaults.baud_rate ?? current.baudRate),
      parity: String(defaults.parity ?? current.parity),
      stopBits: String(defaults.stop_bits ?? current.stopBits),
      byteSize: String(defaults.byte_size ?? current.byteSize),
      timeoutSeconds: String(defaults.timeout_seconds ?? current.timeoutSeconds),
      retries: String(defaults.retries ?? current.retries),
      scanProtocol:
        selectedCatalogEntry.protocol === "aurora"
          ? "aurora"
          : current.scanProtocol === "aurora"
            ? "modbus_rtu"
            : current.scanProtocol,
    }));
  }, [open, scanTransport, selectedCatalogEntry]);

  useEffect(() => {
    if (!open || scanTransport !== "tcp" || selectedCatalogEntry === null) {
      return;
    }
    const operationalTransport =
      linkMode === "gateway_ip" && gatewayUsesRtuOverTcp ? "tcp" : selectedCatalogEntry.transport;
    const defaults = buildProtocolSettings(
      selectedCatalogEntry.protocol,
      selectedCatalogEntry.defaults,
      operationalTransport,
    );
    setNetworkForm((current) => ({
      ...current,
      portStart: String(defaults.port ?? current.portStart),
      portEnd: String(defaults.port ?? current.portEnd),
      timeoutSeconds: String(defaults.timeout_seconds ?? current.timeoutSeconds),
      retries: String(defaults.retries ?? current.retries),
      unitIdStart: String(
        defaults.unit_id ?? defaults.slave_id ?? defaults.address ?? current.unitIdStart,
      ),
      unitIdEnd: String(
        defaults.unit_id ?? defaults.slave_id ?? defaults.address ?? current.unitIdEnd,
      ),
    }));
  }, [gatewayUsesRtuOverTcp, linkMode, open, scanTransport, selectedCatalogEntry]);

  const decoratedResults = useMemo<DecoratedResult[]>(() => {
    if (scanTransport === "serial") {
      return serialResults
        .map((result) => {
          const existingDevice = matchExistingSerialDevice(result, existingDevices);
          const candidateSummary = buildScanCandidateSummary(
            result.candidate_profile_count,
            result.candidate_profiles.map(
              (candidate) => `${candidate.brand} | ${candidate.model} | ${candidate.protocol}`,
            ),
          );
          const compatibility = describeCompatibility(result.candidate_profiles, selectedCatalogEntry);
          return {
            key: `serial:${result.port}:${result.unit_id}`,
            label: `RS485 | ${getSerialPortDisplayName(result.port)} | unit ${result.unit_id}`,
            description:
              result.signature_label?.trim() ||
              `Nodo seriale con register ${result.register} e funzione ${result.function}.`,
            candidateSummary: candidateSummary.headline,
            candidateDetails: candidateSummary.detailLines,
            compatibility,
            existingDevice,
            buildEndpoint: () => {
              const resolvedProtocol = selectedCatalogEntry?.protocol ?? (protocol || "modbus_rtu");
              const resolvedTransport = selectedCatalogEntry?.transport || "serial";
              const defaults =
                selectedCatalogEntry?.defaults ??
                buildProtocolSettings(resolvedProtocol, null, resolvedTransport);
              return {
                key: `serial:${result.port}:${result.unit_id}`,
                label: `RS485 | ${getSerialPortDisplayName(result.port)} | unit ${result.unit_id}`,
                protocol: resolvedProtocol,
                transport: resolvedTransport,
                transportLabel: "Seriale",
                connectionSettings: buildSerialConnectionSettings(
                  resolvedProtocol,
                  defaults,
                  result,
                  serialForm,
                ),
                existingDevice,
                discoveredVia: "serial" as const,
                compatibility,
              };
            },
          };
        })
        .sort((left, right) => {
          if (left.existingDevice === null && right.existingDevice !== null) {
            return -1;
          }
          if (left.existingDevice !== null && right.existingDevice === null) {
            return 1;
          }
          const compatibilityRank = {
            matched_signature: 0,
            candidate_signature: 1,
            unverified_signature: 2,
            manual_selection: 3,
          };
          return compatibilityRank[left.compatibility] - compatibilityRank[right.compatibility];
        });
    }

    return tcpResults
      .map((result) => {
        const existingDevice = matchExistingTcpDevice(result, existingDevices);
        const candidateSummary = buildScanCandidateSummary(
          result.candidate_profile_count,
          result.candidate_profiles.map(
            (candidate) => `${candidate.brand} | ${candidate.model} | ${candidate.protocol}`,
          ),
        );
        const compatibility = describeCompatibility(result.candidate_profiles, selectedCatalogEntry);
        const resolvedProtocol =
          selectedCatalogEntry?.protocol ??
          (gatewayUsesRtuOverTcp ? "modbus_rtu" : protocol || "modbus_tcp");
        const resolvedTransport = "tcp";
        const endpointPrefix =
          linkMode === "gateway_ip"
            ? gatewayUsesRtuOverTcp
              ? "Gateway RTU"
              : "Gateway TCP"
            : "TCP";
        const transportLabel =
          linkMode === "gateway_ip"
            ? gatewayUsesRtuOverTcp
              ? "RTU over TCP"
              : "Modbus TCP"
            : "TCP";
        return {
          key: `tcp:${result.host}:${result.port}:${result.unit_id}`,
          label: `${endpointPrefix} | ${result.host}:${result.port} | unit ${result.unit_id}`,
          description: `Endpoint di rete trovato su ${result.host}:${result.port}.`,
          candidateSummary: candidateSummary.headline,
          candidateDetails: candidateSummary.detailLines,
          compatibility,
          existingDevice,
          buildEndpoint: () => {
            const defaults =
              selectedCatalogEntry?.defaults ??
              buildProtocolSettings(resolvedProtocol, null, resolvedTransport);
            return {
              key: `tcp:${result.host}:${result.port}:${result.unit_id}`,
              label: `${endpointPrefix} | ${result.host}:${result.port} | unit ${result.unit_id}`,
              protocol: resolvedProtocol,
              transport: resolvedTransport,
              transportLabel,
              connectionSettings: buildTcpConnectionSettings(
                resolvedProtocol,
                resolvedTransport,
                defaults,
                result,
                networkForm,
              ),
              existingDevice,
              discoveredVia: linkMode,
              compatibility,
            };
          },
        };
      })
      .sort((left, right) => {
        if (left.existingDevice === null && right.existingDevice !== null) {
          return -1;
        }
        if (left.existingDevice !== null && right.existingDevice === null) {
          return 1;
        }
        const compatibilityRank = {
          matched_signature: 0,
          candidate_signature: 1,
          unverified_signature: 2,
          manual_selection: 3,
        };
        return compatibilityRank[left.compatibility] - compatibilityRank[right.compatibility];
      });
  }, [
    existingDevices,
    linkMode,
    networkForm,
    protocol,
    scanTransport,
    selectedCatalogEntry,
    serialForm,
    serialResults,
    tcpResults,
  ]);

  const decoratedResultMap = useMemo(
    () => new Map(decoratedResults.map((item) => [item.key, item])),
    [decoratedResults],
  );
  const selectedResults = useMemo(
    () =>
      selectedEndpointKeys
        .map((key) => decoratedResultMap.get(key) ?? null)
        .filter((item): item is DecoratedResult => item !== null && item.existingDevice === null),
    [decoratedResultMap, selectedEndpointKeys],
  );
  const plannedNames = useMemo(
    () => buildPlannedDeviceNames(deviceName, selectedResults.length, existingDevices),
    [deviceName, existingDevices, selectedResults.length],
  );
  const selectableResultKeys = useMemo(
    () => decoratedResults.filter((item) => item.existingDevice === null).map((item) => item.key),
    [decoratedResults],
  );
  const selectedCreationPlans = useMemo<SelectedCreationPlan[]>(
    () =>
      selectedResults.map((item, index) => ({
        key: item.key,
        endpoint: item.buildEndpoint(),
        plannedName: plannedNames[index] ?? "",
      })),
    [plannedNames, selectedResults],
  );
  const selectedCreationPlanMap = useMemo(
    () => new Map(selectedCreationPlans.map((plan) => [plan.key, plan])),
    [selectedCreationPlans],
  );
  const selectedEndpoint = useMemo<SelectedEndpoint | null>(() => {
    if (focusedEndpointKey) {
      const selectedPlan = selectedCreationPlanMap.get(focusedEndpointKey);
      if (selectedPlan) {
        return selectedPlan.endpoint;
      }
      const focusedResult = decoratedResultMap.get(focusedEndpointKey);
      if (focusedResult) {
        return focusedResult.buildEndpoint();
      }
    }
    return selectedCreationPlans[0]?.endpoint ?? null;
  }, [decoratedResultMap, focusedEndpointKey, selectedCreationPlanMap, selectedCreationPlans]);

  const canScan = brand.trim() !== "" && model.trim() !== "" && (selectedCatalogEntry !== null || protocol !== "");
  const canTestConnection = selectedCatalogEntry !== null && selectedEndpoint !== null;
  const canCreateDevices = selectedCatalogEntry !== null && selectedCreationPlans.length > 0;
  const selectedCompatibility = selectedEndpoint
    ? buildCompatibilityLabel(selectedEndpoint.compatibility)
    : null;

  function handleDrawerClose() {
    if (scanBusy || protocolOperationState?.active) {
      setScanError("Ferma il browsing in corso o attendi la fine prima di chiudere la configurazione.");
      return;
    }
    onClose();
  }

  async function handleStopScan() {
    const operationId = activeScanOperationIdRef.current ?? protocolOperationState?.operation_id ?? null;
    try {
      const state = await cancelProtocolOperation({
        operation_id: operationId,
        reason: "operator_stop",
      });
      setProtocolOperationState(state);
      setScanInfo("Arresto browsing richiesto. Chiudo le connessioni aperte prima di liberare il flusso.");
    } catch (error) {
      setScanError(error instanceof Error ? error.message : "Impossibile fermare il browsing in corso.");
    }
    scanAbortControllerRef.current?.abort();
  }

  async function handleScan() {
    if (!canScan) {
      setScanError("Compila prima marca, modello e protocollo del dispositivo.");
      return;
    }

    const remoteOperationState = await getProtocolOperationState().catch(() => null);
    if (remoteOperationState?.active) {
      setProtocolOperationState(remoteOperationState);
      setScanError(
        `${describeProtocolOperation(remoteOperationState) ?? "Un'altra operazione protocollo e gia in corso."} Ferma o attendi la fine prima di avviare una nuova scansione.`,
      );
      return;
    }

    const controller = new AbortController();
    const operationId = createProtocolOperationId();
    const operationLabel =
      scanTransport === "serial"
        ? `Browsing RTU ${getSerialPortDisplayName(serialForm.port.trim() || "seriale")}`
        : `Browsing ${linkMode === "gateway_ip" ? "gateway IP" : "TCP"} ${networkForm.hostStart || "host"}:${
            networkForm.portStart || "porta"
          }`;
    scanAbortControllerRef.current = controller;
    activeScanOperationIdRef.current = operationId;
    setScanBusy(true);
    setScanError(null);
    setScanInfo(null);
    setFocusedEndpointKey(null);
    setSelectedEndpointKeys([]);
    setSerialResults([]);
    setTcpResults([]);
    setTestResult(null);
    setTestError(null);
    setCreateError(null);
    setCreateSuccess(null);
    setCreationProgress(null);
    setScanProgress(null);

    try {
      if (scanTransport === "serial") {
        if (!serialForm.port.trim()) {
          throw new Error("Seleziona prima una porta seriale.");
        }
        const slaveIds = buildIntegerRange(serialForm.slaveIdStart, serialForm.slaveIdEnd, 0, 247);
        const slaveIdChunks = chunkItems(slaveIds, RTU_DISCOVERY_MAX_SLAVE_IDS_PER_REQUEST);
        const aggregatedResults = new Map<string, DeviceDiscoveryRtuResult>();
        let totalDurationMs = 0;
        let totalRequestCount = 0;
        let completedUnitCount = 0;
        const chunkErrors: string[] = [];
        setScanProgress({
          mode: "serial",
          total: slaveIds.length,
          completed: 0,
          found: 0,
          currentLabel: `${getSerialPortDisplayName(serialForm.port.trim())} | unit ${slaveIds[0]}-${slaveIds[slaveIds.length - 1]}`,
          status: "running",
          message: `Scansione RTU avviata su ${slaveIds.length} unit ID in ${slaveIdChunks.length} finestre.`,
        });

        for (const slaveIdChunk of slaveIdChunks) {
          if (controller.signal.aborted) {
            break;
          }
          const chunkLabel = `${getSerialPortDisplayName(serialForm.port.trim())} | unit ${slaveIdChunk[0]}-${
            slaveIdChunk[slaveIdChunk.length - 1]
          }`;
          setScanProgress({
            mode: "serial",
            total: slaveIds.length,
            completed: completedUnitCount,
            found: aggregatedResults.size,
            currentLabel: chunkLabel,
            status: "running",
            message: `Sto sondando ${chunkLabel}.`,
          });
          try {
            const response = await discoverRtuDevices({
              port: serialForm.port.trim(),
              operation_id: operationId,
              operation_label: operationLabel,
              preferred_brand: selectedCatalogEntry?.brand ?? brand,
              preferred_model: selectedCatalogEntry?.model ?? model,
              baud_rate: Number(serialForm.baudRate),
              parity: serialForm.parity,
              stop_bits: Number(serialForm.stopBits),
              byte_size: Number(serialForm.byteSize),
              timeout_seconds: Number(serialForm.timeoutSeconds),
              retries: Number(serialForm.retries),
              scan_protocol: serialForm.scanProtocol,
              slave_ids: slaveIdChunk,
            }, { signal: controller.signal });
            totalDurationMs += response.duration_ms;
            totalRequestCount += response.request_count;
            for (const result of response.results) {
              aggregatedResults.set(
                `${result.port}:${result.unit_id}:${result.register}:${result.function}`,
                result,
              );
            }
            completedUnitCount += slaveIdChunk.length;
            setScanProgress({
              mode: "serial",
              total: slaveIds.length,
              completed: completedUnitCount,
              found: aggregatedResults.size,
              currentLabel:
                completedUnitCount >= slaveIds.length
                  ? null
                  : "Prossima finestra RTU",
              status: "running",
              message: `${completedUnitCount}/${slaveIds.length} unit ID verificati, ${aggregatedResults.size} nodi trovati.`,
            });
          } catch (error) {
            if (controller.signal.aborted) {
              break;
            }
            chunkErrors.push(
              `${slaveIdChunk[0]}-${slaveIdChunk[slaveIdChunk.length - 1]}: ${
                error instanceof Error ? error.message : "errore scansione"
              }`,
            );
            setScanProgress({
              mode: "serial",
              total: slaveIds.length,
              completed: completedUnitCount,
              found: aggregatedResults.size,
              currentLabel: "Finestra RTU non riuscita",
              status: "running",
              message: `${completedUnitCount}/${slaveIds.length} unit ID verificati, ${aggregatedResults.size} nodi trovati.`,
            });
          }
        }

        const mergedResults = Array.from(aggregatedResults.values()).sort(
          (left, right) => left.unit_id - right.unit_id,
        );
        setSerialResults(mergedResults);
        if (controller.signal.aborted) {
          setScanInfo(
            mergedResults.length > 0
              ? `Scansione RTU interrotta. Mantengo ${mergedResults.length} nodi gia trovati.`
              : "Scansione RTU interrotta dall'operatore.",
          );
          setScanProgress({
            mode: "serial",
            total: slaveIds.length,
            completed: completedUnitCount,
            found: mergedResults.length,
            currentLabel: null,
            status: "warning",
            message:
              mergedResults.length > 0
                ? `${mergedResults.length} nodi RTU trovati prima dell'interruzione.`
                : "Scansione RTU interrotta prima di trovare nodi.",
          });
          return;
        }
        if (mergedResults.length > 0) {
          setScanInfo(
            `${mergedResults.length} nodi trovati in ${totalDurationMs} ms${
              slaveIdChunks.length > 1 ? ` su ${slaveIdChunks.length} finestre di scansione` : ""
            }${
              chunkErrors.length > 0
                ? `, con ${chunkErrors.length} finestre non riuscite`
                : ""
            }.`,
          );
          if (chunkErrors.length > 0) {
            setScanError(
              `Alcune finestre RTU non sono riuscite: ${chunkErrors.slice(0, 2).join(" | ")}`,
            );
          }
        } else if (chunkErrors.length > 0) {
          setScanError(
            `Nessun nodo trovato. Alcune finestre RTU non sono riuscite: ${chunkErrors
              .slice(0, 3)
              .join(" | ")}`,
          );
          setScanInfo(
            `Scansione RTU completata su ${slaveIdChunks.length} finestre senza risultati utili.`,
          );
        } else {
          setScanInfo("Nessun nodo trovato con i parametri correnti.");
        }
        setScanProgress({
          mode: "serial",
          total: slaveIds.length,
          completed: completedUnitCount,
          found: mergedResults.length,
          currentLabel: null,
          status:
            chunkErrors.length > 0
              ? mergedResults.length > 0
                ? "warning"
                : "error"
              : "success",
          message:
            mergedResults.length > 0
              ? `${mergedResults.length} nodi RTU trovati in ${totalDurationMs} ms su ${totalRequestCount} probe.`
              : chunkErrors.length > 0
                ? "Scansione RTU completata, ma alcune finestre non hanno risposto correttamente."
                : "Scansione RTU completata senza nodi rilevati.",
        });
        return;
      }

      const unitIds = buildIntegerRange(networkForm.unitIdStart, networkForm.unitIdEnd, 0, 247);
      if (!networkForm.hostStart.trim() || !networkForm.hostEnd.trim()) {
        throw new Error("Definisci un intervallo IP valido.");
      }
      const hosts = buildIpv4HostRange(networkForm.hostStart, networkForm.hostEnd);
      const ports = buildIntegerRange(networkForm.portStart, networkForm.portEnd, 1, 65535);
      const endpointCount = hosts.length * ports.length * unitIds.length;
      if (endpointCount > 512) {
        throw new Error(
          `Intervallo troppo ampio per la scansione di rete: ${endpointCount} endpoint da sondare.`,
        );
      }
      const unitIdChunks = chunkItems(unitIds, TCP_DISCOVERY_MAX_UNIT_IDS_PER_REQUEST);
      const scanJobs = hosts.flatMap((host) =>
        ports.flatMap((port) =>
          unitIdChunks.map((unitIdChunk) => ({
            host,
            port,
            unitIds: unitIdChunk,
          })),
        ),
      );
      const aggregatedResults = new Map<string, DeviceDiscoveryTcpResult>();
      const chunkErrors: string[] = [];
      let scannedEndpointCount = 0;
      let totalDurationMs = 0;
      let totalRequestCount = 0;
      setScanProgress({
        mode: linkMode,
        total: endpointCount,
        completed: 0,
        found: 0,
        currentLabel: `${hosts[0]}:${ports[0]} | unit ${unitIds[0]}-${unitIds[unitIds.length - 1]}`,
        status: "running",
        message: `Scansione ${linkMode === "gateway_ip" ? "gateway IP" : "TCP"} avviata su ${endpointCount} endpoint.`,
      });

      for (const job of scanJobs) {
        if (controller.signal.aborted) {
          break;
        }
        const unitLabel =
          job.unitIds.length === 1
            ? `unit ${job.unitIds[0]}`
            : `unit ${job.unitIds[0]}-${job.unitIds[job.unitIds.length - 1]}`;
        const jobLabel = `${job.host}:${job.port} | ${unitLabel}`;
        setScanProgress({
          mode: linkMode,
          total: endpointCount,
          completed: scannedEndpointCount,
          found: aggregatedResults.size,
          currentLabel: jobLabel,
          status: "running",
          message: `Sto sondando ${jobLabel}.`,
        });
        try {
          const response = await discoverTcpDevices({
            host_start: job.host,
            host_end: job.host,
            port_start: job.port,
            port_end: job.port,
            operation_id: operationId,
            operation_label: operationLabel,
            timeout_seconds: Number(networkForm.timeoutSeconds),
            retries: Number(networkForm.retries),
            unit_ids: job.unitIds,
            preferred_brand: selectedCatalogEntry?.brand ?? brand,
            preferred_model: selectedCatalogEntry?.model ?? model,
            gateway_protocol_mode:
              linkMode === "gateway_ip" && gatewayUsesRtuOverTcp ? "rtu_over_tcp" : "tcp",
          }, { signal: controller.signal });
          totalDurationMs += response.duration_ms;
          totalRequestCount += response.request_count;
          for (const result of response.results) {
            aggregatedResults.set(
              `${result.host}:${result.port}:${result.unit_id}:${result.register}:${result.function}`,
              result,
            );
          }
          scannedEndpointCount += job.unitIds.length;
          setScanProgress({
            mode: linkMode,
            total: endpointCount,
            completed: scannedEndpointCount,
            found: aggregatedResults.size,
            currentLabel:
              scannedEndpointCount >= endpointCount
                ? null
                : "Prossimo endpoint di rete",
            status: "running",
            message: `${scannedEndpointCount}/${endpointCount} endpoint verificati, ${aggregatedResults.size} nodi trovati.`,
          });
        } catch (error) {
          if (controller.signal.aborted) {
            break;
          }
          chunkErrors.push(
            `${jobLabel}: ${error instanceof Error ? error.message : "errore scansione"}`,
          );
          setScanProgress({
            mode: linkMode,
            total: endpointCount,
            completed: scannedEndpointCount,
            found: aggregatedResults.size,
            currentLabel: "Blocco di rete non riuscito",
            status: "running",
            message: `${scannedEndpointCount}/${endpointCount} endpoint verificati, ${aggregatedResults.size} nodi trovati.`,
          });
        }
      }

      const mergedResults = Array.from(aggregatedResults.values()).sort(
        (left, right) =>
          left.host.localeCompare(right.host, "it", { numeric: true }) ||
          left.port - right.port ||
          left.unit_id - right.unit_id,
      );
      setTcpResults(mergedResults);
      if (controller.signal.aborted) {
        setScanInfo(
          mergedResults.length > 0
            ? `Scansione ${linkMode === "gateway_ip" ? "gateway IP" : "TCP"} interrotta. Mantengo ${mergedResults.length} endpoint gia trovati.`
            : `Scansione ${linkMode === "gateway_ip" ? "gateway IP" : "TCP"} interrotta dall'operatore.`,
        );
        setScanProgress({
          mode: linkMode,
          total: endpointCount,
          completed: scannedEndpointCount,
          found: mergedResults.length,
          currentLabel: null,
          status: "warning",
          message:
            mergedResults.length > 0
              ? `${mergedResults.length} endpoint trovati prima dell'interruzione.`
              : "Scansione interrotta prima di trovare endpoint.",
        });
        return;
      }
      setScanInfo(
        mergedResults.length > 0
          ? `${mergedResults.length} endpoint trovati in ${totalDurationMs} ms${
              chunkErrors.length > 0 ? `, con ${chunkErrors.length} blocchi non riusciti` : ""
            }.`
          : chunkErrors.length > 0
            ? `Scansione completata senza risultati utili. ${chunkErrors.length} blocchi non sono riusciti.`
            : "Nessun endpoint trovato con i parametri correnti.",
      );
      if (chunkErrors.length > 0) {
        setScanError(
          `Alcuni blocchi di rete non sono riusciti: ${chunkErrors.slice(0, 2).join(" | ")}`,
        );
      }
      setScanProgress({
        mode: linkMode,
        total: endpointCount,
        completed: scannedEndpointCount,
        found: mergedResults.length,
        currentLabel: null,
        status:
          chunkErrors.length > 0
            ? mergedResults.length > 0
              ? "warning"
              : "error"
            : "success",
        message:
          mergedResults.length > 0
            ? `${mergedResults.length} endpoint trovati su ${scannedEndpointCount} controllati.`
            : chunkErrors.length > 0
              ? "Scansione rete completata, ma alcuni blocchi non hanno risposto correttamente."
              : "Scansione rete completata senza endpoint rilevati.",
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Scansione non riuscita.";
      if (controller.signal.aborted) {
        setScanInfo("Scansione interrotta dall'operatore.");
        setScanProgress((current) =>
          current
            ? {
                ...current,
                currentLabel: null,
                status: "warning",
                message: "Scansione interrotta dall'operatore.",
              }
            : {
                mode: linkMode,
                total: 1,
                completed: 0,
                found: 0,
                currentLabel: null,
                status: "warning",
                message: "Scansione interrotta dall'operatore.",
              },
        );
      } else {
        setScanError(errorMessage);
        setScanProgress({
          mode: linkMode,
          total: 1,
          completed: 1,
          found: 0,
          currentLabel: null,
          status: "error",
          message: errorMessage,
        });
      }
    } finally {
      if (activeScanOperationIdRef.current === operationId) {
        try {
          const state = await finishProtocolOperation({ operation_id: operationId });
          setProtocolOperationState(state);
        } catch {
          // The next polling tick will refresh the operation state.
        }
        activeScanOperationIdRef.current = null;
      }
      if (scanAbortControllerRef.current === controller) {
        scanAbortControllerRef.current = null;
      }
      setScanBusy(false);
    }
  }

  async function executeConnectionTest(): Promise<ProtocolTestResult | null> {
    if (selectedCatalogEntry === null || selectedEndpoint === null) {
      setTestError("Seleziona prima un nodo rilevato da usare come endpoint del dispositivo.");
      return null;
    }

    setTestingConnection(true);
    setTestError(null);
    setTestResult(null);

    try {
      const remoteOperationState = await getProtocolOperationState().catch(() => null);
      if (remoteOperationState?.active) {
        setProtocolOperationState(remoteOperationState);
        setTestError(
          `${describeProtocolOperation(remoteOperationState) ?? "Un'altra operazione protocollo e gia in corso."} Ferma o attendi la fine prima di testare la connessione.`,
        );
        return null;
      }
      const normalizedSettings = normalizeConnectionSettings(
        selectedEndpoint.protocol,
        selectedEndpoint.transport,
        selectedEndpoint.connectionSettings,
      );
      const result = await testProtocolConnection({
        protocol: selectedEndpoint.protocol,
        transport: selectedEndpoint.transport,
        brand: selectedCatalogEntry.brand,
        model: selectedCatalogEntry.model,
        connection_settings: normalizedSettings,
        profile_overrides: {},
      });
      setTestResult(result);
      if (!result.success) {
        setTestError(
          buildProvisioningTestErrorMessage(
            result,
            selectedEndpoint,
            selectedEndpoint.transport,
          ),
        );
      }
      return result;
    } catch (error) {
      setTestError(
        buildProvisioningRuntimeErrorMessage(
          error,
          selectedEndpoint,
          selectedEndpoint.transport,
        ),
      );
      return null;
    } finally {
      setTestingConnection(false);
    }
  }

  async function handleCreateDevice() {
    if (!deviceName.trim()) {
      setCreateError("Inserisci un nome dispositivo prima del salvataggio.");
      return;
    }
    if (selectedCatalogEntry === null || selectedCreationPlans.length === 0) {
      setCreateError("Seleziona almeno un nodo valido dalla scansione.");
      return;
    }

    setCreatingDevice(true);
    cancelRequestedRef.current = false;
    setCreateError(null);
    setCreateSuccess(null);
    const creationPlans = selectedCreationPlans;
    setCreationProgress({
      total: creationPlans.length,
      completed: 0,
      currentName: creationPlans[0]?.plannedName ?? null,
      items: creationPlans.map((plan) => ({
        key: plan.key,
        name: plan.plannedName,
        endpointLabel: plan.endpoint.label,
        status: "pending",
        message: "In coda",
      })),
    });
    onClose();

    try {
      const createdNames: string[] = [];
      const createdDevices: Device[] = [];
      const failedCreates: string[] = [];

      for (const [index, plan] of creationPlans.entries()) {
        if (cancelRequestedRef.current) {
          const pendingPlanKeys = new Set(creationPlans.slice(index).map((pendingPlan) => pendingPlan.key));
          failedCreates.push(
            `Configurazione interrotta dall'operatore: ${pendingPlanKeys.size} dispositivi non creati.`,
          );
          setCreationProgress((current) =>
            current
              ? {
                  ...current,
                  completed: current.total,
                  currentName: null,
                  items: current.items.map((item) =>
                    pendingPlanKeys.has(item.key)
                      ? {
                          ...item,
                          status: "error",
                          message: "Interrotto dall'operatore",
                        }
                      : item,
                  ),
                }
              : current,
          );
          break;
        }
        setCreationProgress((current) =>
          current
            ? {
                ...current,
                currentName: plan.plannedName,
                items: current.items.map((item) =>
                  item.key === plan.key
                    ? {
                        ...item,
                        status: "running",
                        message: "Configurazione in corso",
                      }
                    : item,
                ),
              }
            : current,
        );
        try {
          const normalizedSettings = normalizeConnectionSettings(
            plan.endpoint.protocol,
            plan.endpoint.transport,
            plan.endpoint.connectionSettings,
          );
          const device = await createDevice({
            name: plan.plannedName,
            brand: selectedCatalogEntry.brand,
            model: selectedCatalogEntry.model,
            protocol: plan.endpoint.protocol,
            transport: plan.endpoint.transport,
            connection_settings: normalizedSettings,
          });
          createdNames.push(device.name);
          createdDevices.push(device);
          setCreationProgress((current) =>
            current
              ? {
                  ...current,
                  completed: Math.min(current.total, current.completed + 1),
                  currentName: creationPlans[index + 1]?.plannedName ?? null,
                  items: current.items.map((item) =>
                    item.key === plan.key
                      ? {
                          ...item,
                          status: "success",
                          message: "Configurato",
                        }
                      : item,
                  ),
                }
              : current,
          );
        } catch (error) {
          const errorMessage = buildProvisioningRuntimeErrorMessage(
            error,
            plan.endpoint,
            plan.endpoint.transport,
          );
          failedCreates.push(
            `${plan.plannedName || plan.endpoint.label}: ${errorMessage}`,
          );
          setCreationProgress((current) =>
            current
              ? {
                  ...current,
                  completed: Math.min(current.total, current.completed + 1),
                  currentName: creationPlans[index + 1]?.plannedName ?? null,
                  items: current.items.map((item) =>
                    item.key === plan.key
                      ? {
                          ...item,
                          status: "error",
                          message: errorMessage,
                        }
                      : item,
                  ),
                }
              : current,
          );
        }
      }

      if (createdNames.length > 0) {
        await onCreated(createdDevices);
      }

      if (createdNames.length > 0) {
        setCreateSuccess(
          createdNames.length === 1
            ? `${createdNames[0]} e stato aggiunto correttamente alla dashboard operatore.`
            : `${createdNames.length} dispositivi creati: ${createdNames.slice(0, 3).join(", ")}${
                createdNames.length > 3 ? ` e altri ${createdNames.length - 3}` : ""
              }.`,
        );
      }

      if (failedCreates.length > 0) {
        setCreateError(
          failedCreates.length === 1
            ? failedCreates[0]
            : `${failedCreates.length} salvataggi non riusciti. ${failedCreates.slice(0, 2).join(" | ")}`,
        );
      }

      if (createdNames.length > 0 && failedCreates.length === 0) {
        setSelectedEndpointKeys([]);
      }
    } catch (error) {
      setCreateError(
        error instanceof Error ? error.message : "Impossibile salvare il nuovo dispositivo.",
      );
    } finally {
      setCreationProgress((current) =>
        current
          ? {
              ...current,
              currentName: null,
            }
          : current,
      );
      setCreatingDevice(false);
    }
  }

  function handleInterfaceSelection(address: string) {
    const range = buildHostSelectionRange(address);
    setNetworkForm((current) => ({
      ...current,
      interfaceAddress: address,
      hostStart: range?.start ?? current.hostStart,
      hostEnd: range?.end ?? current.hostEnd,
    }));
  }

  function applySuggestedBaseName(endpoint: SelectedEndpoint, label: string) {
    if (deviceName.trim()) {
      return;
    }
    const serialIdentifier =
      findNumericConnectionValue(endpoint.connectionSettings, "slave_id", ["address"]) ?? label;
    const networkIdentifier = findStringConnectionValue(endpoint.connectionSettings, "host") ?? label;
    setDeviceName(
      scanTransport === "serial"
        ? buildSuggestedName(model, "Nodo seriale", serialIdentifier)
        : buildSuggestedName(model, "Nodo rete", networkIdentifier),
    );
  }

  function handleFocusEndpoint(item: DecoratedResult) {
    const endpoint = item.buildEndpoint();
    setFocusedEndpointKey(item.key);
    setTestResult(null);
    setTestError(null);
    setCreateError(null);
    setCreateSuccess(null);
    applySuggestedBaseName(endpoint, item.label);
  }

  function handleEndpointSelection(item: DecoratedResult, selected: boolean) {
    if (item.existingDevice !== null) {
      return;
    }
    setCreationProgress(null);
    const endpoint = item.buildEndpoint();
    setSelectedEndpointKeys((current) => {
      if (selected) {
        return current.includes(item.key) ? current : [...current, item.key];
      }
      return current.filter((key) => key !== item.key);
    });
    setFocusedEndpointKey((current) => {
      if (selected) {
        return current ?? item.key;
      }
      return current === item.key ? null : current;
    });
    setTestResult(null);
    setTestError(null);
    setCreateError(null);
    setCreateSuccess(null);
    if (selected) {
      applySuggestedBaseName(endpoint, item.label);
    }
  }

  function handleSelectAllResults() {
    setCreationProgress(null);
    setSelectedEndpointKeys(selectableResultKeys);
    if (!focusedEndpointKey && selectableResultKeys.length > 0) {
      setFocusedEndpointKey(selectableResultKeys[0]);
    }
    setCreateError(null);
    setCreateSuccess(null);
  }

  function handleClearSelectedResults() {
    setCreationProgress(null);
    setSelectedEndpointKeys([]);
    setCreateError(null);
    setCreateSuccess(null);
  }

  if (!open) {
    return null;
  }

  const section = SETTINGS_SECTION_CONTENT.com;
  const protocolOperationDescription = describeProtocolOperation(protocolOperationState);
  const protocolOperationBlocksScan = !scanBusy && protocolOperationState?.active === true;

  return (
    <div className="device-discovery-shell device-discovery-shell--open" aria-hidden={!open}>
      <div
        className="modal-backdrop"
        role="presentation"
        onClick={handleDrawerClose}
      >
        <aside
          className={`modal-panel modal-panel--wide operator-provision-panel settings-accent-shell ${getSettingsAccentClass(
            "com",
          )}`}
          aria-label="Configurazione dispositivi operatore"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="modal-header">
            <div>
              <p className="panel-kicker">{section.eyebrow}</p>
              <h2>{section.drawerTitle}</h2>
              <p className="field-note">
                {section.drawerCopy}
              </p>
              <div className="settings-accent-pill-row">
                <span className={`settings-accent-pill ${getSettingsAccentClass("com")}`}>
                  {section.legendLabel}
                </span>
              </div>
            </div>
            <button className="icon-button" type="button" onClick={handleDrawerClose}>
              Chiudi
            </button>
          </div>

          <div className="modal-body operator-provision-body">
            <ul className="settings-guidance-list settings-guidance-list--tight">
              {section.guidance.map((item) => (
                <li key={`${item.label}:${item.text}`}>
                  <strong>{item.label}</strong>
                  <span>{item.text}</span>
                </li>
              ))}
            </ul>

            {loadingSetup ? (
              <div className="panel-state">Caricamento catalogo, porte seriali e interfacce...</div>
            ) : null}
            {setupError ? (
              <div className="panel-state panel-state--error" role="alert">
                {setupError}
              </div>
            ) : null}

            <section className="wizard-stage-panel">
              <div className="wizard-stage-panel-head">
                <div>
                  <p className="panel-kicker">1. Identita e collegamento</p>
                  <h3>Definisci il profilo inverter da cercare</h3>
                </div>
                <div className="wizard-chip-list">
                  <span className="wizard-chip">Operatore</span>
                  <span className="wizard-chip">Provisioning unificato</span>
                </div>
              </div>

              <div className="form-grid">
                <label className="field">
                  <span className="field-label">Nome dispositivo</span>
                  <input
                    className="field-control"
                    type="text"
                    value={deviceName}
                    onChange={(event) => setDeviceName(event.currentTarget.value)}
                    placeholder="Es. Inverter tetto sud"
                  />
                </label>
                <label className="field">
                  <span className="field-label">Collegamento</span>
                  <div className="operator-provision-mode-switch">
                    {[
                      { value: "serial", label: "Seriale" },
                      { value: "tcp", label: "TCP" },
                      { value: "gateway_ip", label: "Gateway IP" },
                    ].map((option) => (
                      <button
                        key={option.value}
                        className={`operator-provision-mode-switch__button ${
                          linkMode === option.value
                            ? "operator-provision-mode-switch__button--active"
                            : ""
                        }`}
                        type="button"
                        onClick={() => setLinkMode(option.value as ProvisioningLinkMode)}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </label>
                <label className="field">
                  <span className="field-label">Marca</span>
                  <select
                    className="field-control"
                    value={brand}
                    onChange={(event) => {
                      setBrand(event.currentTarget.value);
                      setModel("");
                      setProtocol("");
                    }}
                  >
                    <option value="">Seleziona marca</option>
                    {brandOptions.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span className="field-label">Modello</span>
                  <select
                    className="field-control"
                    value={model}
                    onChange={(event) => {
                      setModel(event.currentTarget.value);
                      setProtocol("");
                    }}
                    disabled={!brand}
                  >
                    <option value="">Seleziona modello</option>
                    {modelOptions.map((catalogModel) => (
                      <option key={catalogModel.model} value={catalogModel.model}>
                        {catalogModel.model}
                      </option>
                    ))}
                  </select>
                </label>
                {linkMode === "gateway_ip" ? (
                  <label className="field">
                    <span className="field-label">Protocollo gateway</span>
                    <select
                      className="field-control"
                      value={gatewayProtocolMode}
                      onChange={(event) =>
                        setGatewayProtocolMode(event.currentTarget.value as GatewayProtocolMode)
                      }
                    >
                      <option value="rtu_over_tcp">RTU over TCP</option>
                      <option value="tcp">Modbus TCP</option>
                    </select>
                  </label>
                ) : null}
                {protocolOptions.length > 1 ? (
                  <label className="field">
                    <span className="field-label">Protocollo</span>
                    <select
                      className="field-control"
                      value={protocol}
                      onChange={(event) => setProtocol(event.currentTarget.value)}
                    >
                      <option value="">Seleziona protocollo</option>
                      {protocolOptions.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <div className="field">
                    <span className="field-label">Protocollo operativo</span>
                    <div className="operator-provision-inline-value">
                      {selectedCatalogEntry?.protocol || "Seleziona prima un modello"}
                    </div>
                  </div>
                )}
                <div className="field">
                  <span className="field-label">Nota collegamento</span>
                  <div className="operator-provision-note-card">
                    {linkMode === "serial"
                      ? "Userai la scansione RS485 per trovare gli unit/slave id disponibili sulla porta seriale scelta."
                      : linkMode === "gateway_ip"
                        ? gatewayUsesRtuOverTcp
                          ? "Gateway IP usa un convertitore RS485/TCP e parla Modbus RTU incapsulato su TCP. Qui vedi i profili RTU, ma il dispositivo verra configurato con trasporto TCP."
                          : "Gateway IP usa una scansione Modbus TCP diretta verso il gateway. Qui vedi i profili gia compatibili col trasporto TCP."
                        : "Userai la scansione TCP diretta per cercare host e unit id raggiungibili in rete."}
                  </div>
                </div>
              </div>
            </section>

            <section className="wizard-stage-panel">
              <div className="wizard-stage-panel-head">
                <div>
                  <p className="panel-kicker">2. Scansione</p>
                  <h3>Trova i nodi disponibili</h3>
                </div>
                <div className="wizard-chip-list">
                  <span className={`wizard-chip ${canScan ? "wizard-chip--positive" : ""}`}>
                    {canScan ? "Profilo pronto" : "Completa il profilo"}
                  </span>
                </div>
              </div>

              {scanTransport === "serial" ? (
                <div className="form-grid">
                  <label className="field">
                    <span className="field-label">Porta seriale</span>
                    <select
                      className="field-control"
                      value={serialForm.port}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setSerialForm((current) => ({ ...current, port: value }));
                      }}
                    >
                      <option value="">Seleziona porta</option>
                      {serialPortOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">Protocollo scan</span>
                    <select
                      className="field-control"
                      value={serialForm.scanProtocol}
                      onChange={(event) => {
                        const value = event.currentTarget.value as RtuDiscoveryProtocol;
                        setSerialForm((current) => ({
                          ...current,
                          scanProtocol: value,
                        }));
                      }}
                    >
                      <option value="modbus_rtu">Modbus RTU</option>
                      <option value="aurora">Aurora</option>
                      <option value="auto">Auto</option>
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">Baud rate</span>
                    <input
                      className="field-control"
                      type="number"
                      value={serialForm.baudRate}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setSerialForm((current) => ({ ...current, baudRate: value }));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Parita</span>
                    <select
                      className="field-control"
                      value={serialForm.parity}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setSerialForm((current) => ({ ...current, parity: value }));
                      }}
                    >
                      {PARITY_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">Stop bit</span>
                    <input
                      className="field-control"
                      type="number"
                      min={1}
                      max={2}
                      value={serialForm.stopBits}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setSerialForm((current) => ({ ...current, stopBits: value }));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Byte size</span>
                    <input
                      className="field-control"
                      type="number"
                      min={7}
                      max={8}
                      value={serialForm.byteSize}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setSerialForm((current) => ({ ...current, byteSize: value }));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Timeout connessione (s)</span>
                    <input
                      className="field-control"
                      type="number"
                      min={0.05}
                      step={0.05}
                      value={serialForm.timeoutSeconds}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setSerialForm((current) => ({ ...current, timeoutSeconds: value }));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Slave iniziale</span>
                    <input
                      className="field-control"
                      type="number"
                      min={0}
                      max={247}
                      value={serialForm.slaveIdStart}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setSerialForm((current) => ({
                          ...current,
                          slaveIdStart: value,
                        }));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Slave finale</span>
                    <input
                      className="field-control"
                      type="number"
                      min={0}
                      max={247}
                      value={serialForm.slaveIdEnd}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setSerialForm((current) => ({
                          ...current,
                          slaveIdEnd: value,
                        }));
                      }}
                    />
                  </label>
                </div>
              ) : (
                <div className="form-grid">
                  <label className="field">
                    <span className="field-label">Scheda di rete</span>
                    <select
                      className="field-control"
                      value={networkForm.interfaceAddress}
                      onChange={(event) => handleInterfaceSelection(event.currentTarget.value)}
                    >
                      <option value="">Seleziona interfaccia</option>
                      {networkInterfaceOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">IP iniziale</span>
                    <input
                      className="field-control"
                      type="text"
                      value={networkForm.hostStart}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setNetworkForm((current) => ({ ...current, hostStart: value }));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">IP finale</span>
                    <input
                      className="field-control"
                      type="text"
                      value={networkForm.hostEnd}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setNetworkForm((current) => ({ ...current, hostEnd: value }));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Porta iniziale</span>
                    <input
                      className="field-control"
                      type="number"
                      min={1}
                      max={65535}
                      value={networkForm.portStart}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setNetworkForm((current) => ({ ...current, portStart: value }));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Porta finale</span>
                    <input
                      className="field-control"
                      type="number"
                      min={1}
                      max={65535}
                      value={networkForm.portEnd}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setNetworkForm((current) => ({ ...current, portEnd: value }));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Timeout connessione (s)</span>
                    <input
                      className="field-control"
                      type="number"
                      min={0.05}
                      step={0.05}
                      value={networkForm.timeoutSeconds}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setNetworkForm((current) => ({ ...current, timeoutSeconds: value }));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Unit iniziale</span>
                    <input
                      className="field-control"
                      type="number"
                      min={0}
                      max={247}
                      value={networkForm.unitIdStart}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setNetworkForm((current) => ({
                          ...current,
                          unitIdStart: value,
                        }));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Unit finale</span>
                    <input
                      className="field-control"
                      type="number"
                      min={0}
                      max={247}
                      value={networkForm.unitIdEnd}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setNetworkForm((current) => ({
                          ...current,
                          unitIdEnd: value,
                        }));
                      }}
                    />
                  </label>
                </div>
              )}

              <div className="wizard-verify-actions">
                <button
                  className={`action-button ${scanBusy ? "action-button--busy" : ""}`}
                  type="button"
                  onClick={() => void handleScan()}
                  disabled={loadingSetup || scanBusy || protocolOperationBlocksScan}
                >
                  {scanBusy
                    ? "Scansione in corso..."
                    : protocolOperationBlocksScan
                      ? "Browsing gia in corso"
                      : "Avvia scansione"}
                </button>
                {scanBusy || protocolOperationBlocksScan ? (
                  <button className="chip-inline-button" type="button" onClick={() => void handleStopScan()}>
                    Interrompi scansione
                  </button>
                ) : null}
                {scanInfo ? <span className="field-note">{scanInfo}</span> : null}
                {protocolOperationDescription ? (
                  <span className="field-note">{protocolOperationDescription}</span>
                ) : null}
              </div>

              {scanProgress ? (
                <OperatorScanProgressPanel
                  progress={scanProgress}
                  busy={scanBusy}
                  onCancel={scanBusy ? handleStopScan : undefined}
                  onDismiss={() => setScanProgress(null)}
                />
              ) : null}

              {scanError ? (
                <div className="panel-state panel-state--error" role="alert">
                  {scanError}
                </div>
              ) : null}
            </section>

            <section className="wizard-stage-panel">
              <div className="wizard-stage-panel-head">
                <div>
                  <p className="panel-kicker">3. Nodo rilevato</p>
                  <h3>Seleziona i nodi da associare</h3>
                </div>
                <div className="operator-provision-results-toolbar">
                  <div className="wizard-chip-list">
                    <span className="wizard-chip">
                      {decoratedResults.length > 0
                        ? `${decoratedResults.length} nodi disponibili`
                        : "Nessun nodo selezionato"}
                    </span>
                    <span
                      className={`wizard-chip ${selectedCreationPlans.length > 0 ? "wizard-chip--positive" : ""}`}
                    >
                      {selectedCreationPlans.length > 0
                        ? `${selectedCreationPlans.length} selezionati`
                        : "Nessun nodo selezionato"}
                    </span>
                  </div>
                  {selectableResultKeys.length > 0 ? (
                    <div className="operator-provision-results-toolbar__actions">
                      <button className="chip-inline-button" type="button" onClick={handleSelectAllResults}>
                        Seleziona tutti
                      </button>
                      <button
                        className="chip-inline-button"
                        type="button"
                        onClick={handleClearSelectedResults}
                      >
                        Deseleziona tutti
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>

              {decoratedResults.length > 0 ? (
                <div className="operator-provision-results">
                  {decoratedResults.map((item) => {
                    const compatibility = buildCompatibilityLabel(item.compatibility);
                    const isActive = selectedEndpoint?.key === item.key;
                    const isSelected = selectedCreationPlanMap.has(item.key);
                    const plannedName = selectedCreationPlanMap.get(item.key)?.plannedName ?? null;
                    return (
                      <article
                        key={item.key}
                        className={`operator-provision-result-card ${
                          isActive ? "operator-provision-result-card--active" : ""
                        } ${
                          item.existingDevice !== null
                            ? "operator-provision-result-card--configured"
                            : ""
                        }`}
                      >
                        <div className="operator-provision-result-card__head">
                          <div>
                            <strong>{item.label}</strong>
                            <p>{item.description}</p>
                          </div>
                          <span
                            className={`wizard-chip ${
                              compatibility.tone === "positive"
                                ? "wizard-chip--positive"
                                : compatibility.tone === "warning"
                                  ? "wizard-chip--warning"
                                  : ""
                            }`}
                          >
                            {compatibility.label}
                          </span>
                        </div>
                        <div className="operator-provision-result-card__body">
                          <p>{item.candidateSummary}</p>
                          {item.candidateDetails.length > 0 ? (
                            <ul className="operator-provision-result-card__list">
                              {item.candidateDetails.map((detail) => (
                                <li key={detail}>{detail}</li>
                              ))}
                            </ul>
                          ) : null}
                          {item.existingDevice !== null ? (
                            <p className="operator-provision-result-card__configured-note">
                              Gia configurato come <strong>{item.existingDevice.name}</strong>.
                            </p>
                          ) : null}
                          {plannedName ? (
                            <p className="operator-provision-result-card__selected-note">
                              Nome previsto: <strong>{plannedName}</strong>
                            </p>
                          ) : null}
                        </div>
                        <div className="operator-provision-result-card__actions">
                          {item.existingDevice === null ? (
                            <label className="operator-provision-result-card__checkbox">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={(event) =>
                                  handleEndpointSelection(item, event.currentTarget.checked)
                                }
                              />
                              <span>{isSelected ? "Selezionato" : "Seleziona"}</span>
                            </label>
                          ) : null}
                          <button
                            className="secondary-button"
                            type="button"
                            onClick={() => handleFocusEndpoint(item)}
                          >
                            {isActive ? "Nodo in focus" : "Usa per test"}
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <div className="operator-provision-empty">
                  Nessun nodo disponibile. Definisci il profilo e avvia una scansione per vedere i
                  risultati qui.
                </div>
              )}
            </section>

            <section className="wizard-stage-panel">
              <div className="wizard-stage-panel-head">
                <div>
                  <p className="panel-kicker">4. Verifica e salvataggio</p>
                  <h3>Conferma il profilo prima di creare il device</h3>
                </div>
              </div>

              <div className="wizard-review-grid">
                <article className="wizard-review-card">
                  <div className="wizard-review-block-head">
                    <strong>Profilo selezionato</strong>
                  </div>
                  <div className="wizard-review-block">
                    <div>
                      <span>Nome base</span>
                      <strong>{deviceName.trim() || "--"}</strong>
                    </div>
                    <div>
                      <span>Marca e modello</span>
                      <strong>
                        {selectedCatalogEntry
                          ? `${selectedCatalogEntry.brand} | ${selectedCatalogEntry.model}`
                          : "--"}
                      </strong>
                    </div>
                    <div>
                      <span>Protocollo</span>
                      <strong>{selectedCatalogEntry?.protocol || "--"}</strong>
                    </div>
                    <div>
                      <span>Collegamento</span>
                      <strong>
                        {linkMode === "serial"
                          ? "Seriale"
                          : linkMode === "gateway_ip"
                            ? "Gateway IP"
                          : "TCP"}
                      </strong>
                    </div>
                    <div>
                      <span>Nodi selezionati</span>
                      <strong>{selectedCreationPlans.length > 0 ? selectedCreationPlans.length : "--"}</strong>
                    </div>
                  </div>
                </article>

                <article className="wizard-review-card">
                  <div className="wizard-review-block-head">
                    <strong>Focus e creazione batch</strong>
                  </div>
                  <div className="wizard-review-block">
                    <div>
                      <span>Nodo in focus</span>
                      <strong>{selectedEndpoint?.label || "--"}</strong>
                    </div>
                    <div>
                      <span>Trasporto operativo</span>
                      <strong>{selectedEndpoint?.transportLabel || "--"}</strong>
                    </div>
                    <div>
                      <span>Esito firma</span>
                      <strong>{selectedCompatibility?.label || "--"}</strong>
                    </div>
                    <div>
                      <span>Duplice configurazione</span>
                      <strong>
                        {selectedEndpoint?.existingDevice
                          ? `Gia presente: ${selectedEndpoint.existingDevice.name}`
                          : "Nessuna"}
                      </strong>
                    </div>
                    <div>
                      <span>Anteprima nomi</span>
                      <strong>
                        {selectedCreationPlans.length > 0
                          ? selectedCreationPlans
                              .slice(0, 3)
                              .map((plan) => plan.plannedName)
                              .join(", ")
                          : "--"}
                      </strong>
                    </div>
                  </div>
                </article>
              </div>

              <div className="wizard-verify-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => void executeConnectionTest()}
                  disabled={!canTestConnection || testingConnection || creatingDevice}
                >
                  {testingConnection ? "Verifica in corso..." : "Testa connessione"}
                </button>
                <button
                  className={`action-button ${creatingDevice ? "action-button--busy" : ""}`}
                  type="button"
                  onClick={() => void handleCreateDevice()}
                  disabled={
                    creatingDevice ||
                    !canCreateDevices
                  }
                >
                  {creatingDevice
                    ? "Creazione in corso..."
                    : selectedCreationPlans.length <= 1
                      ? "Crea dispositivo"
                      : `Crea ${selectedCreationPlans.length} dispositivi`}
                </button>
              </div>

              {testResult ? (
                <div
                  className={`panel-state ${
                    testResult.success ? "panel-state--success" : "panel-state--error"
                  }`}
                  role="status"
                >
                  {translateTestMessage(testResult.message)}
                </div>
              ) : null}
              {testError ? (
                <div className="panel-state panel-state--error" role="alert">
                  {testError}
                </div>
              ) : null}
              {createError ? (
                <div className="panel-state panel-state--error" role="alert">
                  {createError}
                </div>
              ) : null}
              {createSuccess ? (
                <div className="panel-state panel-state--success" role="status">
                  {createSuccess}
                </div>
              ) : null}
            </section>
          </div>
        </aside>
      </div>
    </div>
  );
}
