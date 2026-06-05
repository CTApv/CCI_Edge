import { useEffect, useMemo, useState } from "react";

import {
  cancelProtocolOperation,
  discoverRtuDevices,
  discoverTcpDevices,
  finishProtocolOperation,
  getProtocolOperationState,
  type Device,
  getNetworkInterfaces,
  getSerialPorts,
  type ConnectionSettings,
  type DeviceDiscoveryRtuResult,
  type DeviceDiscoveryTcpResult,
  type DiscoveryCandidateProfile,
  type NetworkInterfaceInfo,
  type ProtocolOperationState,
  type RtuDiscoveryProtocol,
  type SerialPortInfo,
} from "../api";
import { useRef } from "react";
import {
  buildSerialPortLabel,
  getSerialPortDisplayName,
} from "./deviceProvisioningShared";

type DeviceDiscoveryModalProps = {
  open: boolean;
  onClose: () => void;
  existingDevices: Device[];
  onBrowsingStateChange: (running: boolean) => void;
  onResultCountChange: (count: number) => void;
  onSelectResult: (prefill: DeviceDiscoveryPrefill) => void;
};

export type DeviceDiscoveryPrefill = {
  name: string;
  brand: string;
  model: string;
  protocol: string;
  transport: string;
  connectionSettings: ConnectionSettings;
  sourceLabel: string;
  candidateProfiles: DiscoveryCandidateProfile[];
  candidateProfileCount: number;
};

type DiscoveryTab = "serial" | "tcp";
type DiscoveryFilter = "all" | "new" | "configured";

type SerialDiscoveryForm = {
  scanProtocol: RtuDiscoveryProtocol;
  port: string;
  baudRate: string;
  parity: string;
  stopBits: string;
  byteSize: string;
  timeoutSeconds: string;
  retries: string;
  slaveIdStart: string;
  slaveIdEnd: string;
};

type TcpDiscoveryForm = {
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

type SerialDiscoveryPreset = {
  title: string;
  label: string;
  copy: string;
  note: string;
  actionLabel: string;
  defaults: Pick<
    SerialDiscoveryForm,
    "baudRate" | "parity" | "stopBits" | "byteSize" | "timeoutSeconds" | "retries"
  >;
};

const SERIAL_DEFAULTS: SerialDiscoveryForm = {
  scanProtocol: "modbus_rtu",
  port: "",
  baudRate: "9600",
  parity: "N",
  stopBits: "1",
  byteSize: "8",
  timeoutSeconds: "0.35",
  retries: "0",
  slaveIdStart: "1",
  slaveIdEnd: "32",
};

const TCP_DEFAULTS: TcpDiscoveryForm = {
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
const SERIAL_DISCOVERY_PROTOCOL_OPTIONS: Array<{
  value: RtuDiscoveryProtocol;
  label: string;
}> = [
  { value: "modbus_rtu", label: "Modbus RTU" },
  { value: "aurora", label: "Aurora" },
  { value: "auto", label: "Auto" },
];
const SERIAL_DISCOVERY_PRESETS: Record<RtuDiscoveryProtocol, SerialDiscoveryPreset> = {
  modbus_rtu: {
    title: "Browsing RS485 / Modbus RTU",
    label: "Modbus RTU",
    copy: "Usa il probe Modbus RTU classico con CRC standard sui registri di discovery del catalogo.",
    note: "Percorso consigliato per inverter RTU standard. Per ABB / Power-One Aurora seleziona la modalita dedicata.",
    actionLabel: "Avvia browsing Modbus RTU",
    defaults: {
      baudRate: "9600",
      parity: "N",
      stopBits: "1",
      byteSize: "8",
      timeoutSeconds: "0.35",
      retries: "0",
    },
  },
  aurora: {
    title: "Browsing RS485 / Aurora",
    label: "Aurora",
    copy: "Usa il probe Aurora dedicato con frame proprietarie e CRC Aurora, separato dal browsing Modbus.",
    note: "Percorso consigliato per Power-One / ABB Aurora. Il probe usa op 50 e, quando disponibile, la firma versione op 58.",
    actionLabel: "Avvia browsing Aurora",
    defaults: {
      baudRate: "19200",
      parity: "N",
      stopBits: "1",
      byteSize: "8",
      timeoutSeconds: "0.5",
      retries: "1",
    },
  },
  auto: {
    title: "Browsing RS485 / Auto",
    label: "Auto",
    copy: "Esegue prima il probe Modbus RTU e poi i fallback dedicati come Aurora quando il nodo non si risolve.",
    note: "Utile solo se non conosci il protocollo. Richiede piu probe e puo essere piu lento del browsing dedicato.",
    actionLabel: "Avvia browsing automatico",
    defaults: {
      baudRate: "9600",
      parity: "N",
      stopBits: "1",
      byteSize: "8",
      timeoutSeconds: "0.35",
      retries: "0",
    },
  },
};

function createDiscoveryOperationId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `browse-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function describeDiscoveryOperation(state: ProtocolOperationState | null): string | null {
  if (!state?.active) {
    return null;
  }
  const label = state.label || state.kind || "browsing";
  const connections = state.active_connections === 1 ? "1 connessione" : `${state.active_connections} connessioni`;
  return state.cancel_requested
    ? `${label}: arresto in corso, ${connections} aperte.`
    : `${label}: ${connections} aperte.`;
}

type DecoratedSerialResult = {
  kind: "serial";
  result: DeviceDiscoveryRtuResult;
  existingDevice: Device | null;
};

type DecoratedTcpResult = {
  kind: "tcp";
  result: DeviceDiscoveryTcpResult;
  existingDevice: Device | null;
};

type DecoratedDiscoveryResult = DecoratedSerialResult | DecoratedTcpResult;

type DiscoveryGroup<T extends DecoratedDiscoveryResult> = {
  key: string;
  label: string;
  items: T[];
  newCount: number;
  configuredCount: number;
  configuredOfflineCount: number;
};

function applySerialDiscoveryPreset(
  current: SerialDiscoveryForm,
  scanProtocol: RtuDiscoveryProtocol,
): SerialDiscoveryForm {
  const preset = SERIAL_DISCOVERY_PRESETS[scanProtocol];
  return {
    ...current,
    scanProtocol,
    ...preset.defaults,
  };
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

function formatScanRawValues(values: number[]): string {
  return values
    .map((value) => `${value} | 0x${value.toString(16).padStart(4, "0").toUpperCase()}`)
    .join(", ");
}

function formatCandidateHeadline(candidates: DiscoveryCandidateProfile[]): string {
  if (candidates.length === 0) {
    return "Profilo da associare manualmente";
  }
  if (candidates.length === 1) {
    return `${candidates[0].brand} | ${candidates[0].model}`;
  }
  const brands = Array.from(new Set(candidates.map((candidate) => candidate.brand)));
  if (brands.length === 1) {
    return `${brands[0]} | ${candidates.length} modelli compatibili`;
  }
  return `${brands.slice(0, 3).join(" | ")}${brands.length > 3 ? " ..." : ""}`;
}

function formatCandidateCount(candidates: DiscoveryCandidateProfile[]): string {
  if (candidates.length === 0) {
    return "Modello da associare manualmente";
  }
  if (candidates.length === 1) {
    return "1 profilo compatibile";
  }
  return `${candidates.length} profili compatibili`;
}

function topCandidateLabels(candidates: DiscoveryCandidateProfile[]): string[] {
  return candidates.slice(0, 3).map((candidate) => `${candidate.brand} | ${candidate.model}`);
}

function findNumericConnectionValue(
  settings: ConnectionSettings,
  primaryKey: string,
  aliases: string[] = [],
): number | null {
  for (const key of [primaryKey, ...aliases]) {
    const value = settings[key];
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
  primaryKey: string,
  aliases: string[] = [],
): string {
  for (const key of [primaryKey, ...aliases]) {
    const value = settings[key];
    if (typeof value === "string" && value.trim() !== "") {
      return value.trim();
    }
  }
  return "";
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
      const unitId = findNumericConnectionValue(device.connection_settings, "unit_id", ["slave_id"]);
      return host === result.host && port === result.port && unitId === result.unit_id;
    }) ?? null
  );
}

function filterDiscoveryItems<T extends { existingDevice: Device | null }>(
  items: T[],
  activeFilter: DiscoveryFilter,
): T[] {
  switch (activeFilter) {
    case "new":
      return items.filter((item) => item.existingDevice === null);
    case "configured":
      return items.filter((item) => item.existingDevice !== null);
    default:
      return items;
  }
}

function normalizeDeviceStatus(status: string | null | undefined): "online" | "offline" | "attention" {
  if (!status) {
    return "offline";
  }
  const normalized = status.trim().toLowerCase();
  if (normalized === "online") {
    return "online";
  }
  if (normalized === "warning" || normalized === "fault") {
    return "attention";
  }
  return "offline";
}

function formatExistingDevicePresence(device: Device | null): string {
  const normalizedStatus = normalizeDeviceStatus(device?.status);
  switch (normalizedStatus) {
    case "online":
      return "Gia in dashboard | online";
    case "attention":
      return "Gia in dashboard | attenzione";
    default:
      return "Gia in dashboard | offline";
  }
}

function isExistingDeviceOffline(device: Device | null): boolean {
  return normalizeDeviceStatus(device?.status) !== "online";
}

function buildGroupLabel(item: DecoratedDiscoveryResult): string {
  if (item.kind === "serial") {
    return `Bus RS485 | ${getSerialPortDisplayName(item.result.port)}`;
  }
  return `Gateway TCP | ${item.result.host}:${item.result.port}`;
}

function buildGroupKey(item: DecoratedDiscoveryResult): string {
  if (item.kind === "serial") {
    return `serial:${item.result.port}`;
  }
  return `tcp:${item.result.host}:${item.result.port}`;
}

function buildDiscoveryGroups<T extends DecoratedDiscoveryResult>(items: T[]): DiscoveryGroup<T>[] {
  const groups = new Map<string, DiscoveryGroup<T>>();
  for (const item of items) {
    const key = buildGroupKey(item);
    const existingGroup = groups.get(key);
    if (existingGroup) {
      existingGroup.items.push(item);
      if (item.existingDevice === null) {
        existingGroup.newCount += 1;
      } else {
        existingGroup.configuredCount += 1;
        if (isExistingDeviceOffline(item.existingDevice)) {
          existingGroup.configuredOfflineCount += 1;
        }
      }
      continue;
    }
    groups.set(key, {
      key,
      label: buildGroupLabel(item),
      items: [item],
      newCount: item.existingDevice === null ? 1 : 0,
      configuredCount: item.existingDevice === null ? 0 : 1,
      configuredOfflineCount:
        item.existingDevice !== null && isExistingDeviceOffline(item.existingDevice) ? 1 : 0,
    });
  }
  return [...groups.values()];
}

function sortDecoratedDiscoveryItems<
  T extends {
    existingDevice: Device | null;
    result: {
      candidate_profile_count: number;
      unit_id: number;
    };
  },
>(items: T[]): T[] {
  return [...items].sort((left, right) => {
    const leftConfigured = left.existingDevice !== null ? 1 : 0;
    const rightConfigured = right.existingDevice !== null ? 1 : 0;
    if (leftConfigured !== rightConfigured) {
      return leftConfigured - rightConfigured;
    }
    const leftOffline = left.existingDevice !== null && isExistingDeviceOffline(left.existingDevice) ? 0 : 1;
    const rightOffline = right.existingDevice !== null && isExistingDeviceOffline(right.existingDevice) ? 0 : 1;
    if (leftOffline !== rightOffline) {
      return leftOffline - rightOffline;
    }
    if (left.result.candidate_profile_count !== right.result.candidate_profile_count) {
      return left.result.candidate_profile_count - right.result.candidate_profile_count;
    }
    return left.result.unit_id - right.result.unit_id;
  });
}

function formatRecommendedAction(
  isConfigured: boolean,
  candidateProfileCount: number,
): string {
  if (isConfigured) {
    return "Nodo gia monitorato: gestiscilo dall'elenco dispositivi.";
  }
  if (candidateProfileCount === 0) {
    return "Nodo trovato: associa marca e modello manualmente prima del test connessione.";
  }
  if (candidateProfileCount === 1) {
    return "Pronto per l'aggiunta: apri il form, verifica il profilo suggerito e testa la connessione.";
  }
  return "Nodo trovato: scegli uno dei profili suggeriti nel form e verifica il modello corretto.";
}

function describeDiscoverySignature(candidateProfileCount: number): {
  label: string;
  tone: "positive" | "neutral" | "warning";
} {
  if (candidateProfileCount === 0) {
    return { label: "Firma non risolta", tone: "warning" };
  }
  if (candidateProfileCount === 1) {
    return { label: "Firma univoca", tone: "positive" };
  }
  return { label: "Firma di famiglia", tone: "neutral" };
}

function formatDiscoverySignatureLine(
  candidates: DiscoveryCandidateProfile[],
  result: DeviceDiscoveryRtuResult | DeviceDiscoveryTcpResult,
): string {
  if ("signature_label" in result && typeof result.signature_label === "string" && result.signature_label) {
    return `Probe Aurora op ${result.register} | ${result.signature_label}`;
  }
  const protocols = Array.from(new Set(candidates.map((candidate) => candidate.protocol)));
  if (protocols.length === 1 && protocols[0] === "aurora") {
    return `Probe Aurora op ${result.register} | CRC Aurora dedicato`;
  }
  return `Registro ${result.register} | funzione ${result.function}`;
}

function buildSerialPrefill(result: DeviceDiscoveryRtuResult): DeviceDiscoveryPrefill {
  const candidates = result.candidate_profiles;
  const uniqueBrands = Array.from(new Set(candidates.map((candidate) => candidate.brand)));
  const uniqueProtocols = Array.from(new Set(candidates.map((candidate) => candidate.protocol)));
  const exactCandidate = candidates.length === 1 ? candidates[0] : null;
  const protocol = exactCandidate?.protocol ?? uniqueProtocols[0] ?? "modbus_rtu";
  const brand = exactCandidate?.brand ?? (uniqueBrands.length === 1 ? uniqueBrands[0] : "");
  const model = exactCandidate?.model ?? "";
  let connectionSettings: ConnectionSettings;
  if (protocol === "aurora") {
    connectionSettings = {
      port: result.port,
      address: result.unit_id,
      baud_rate: 19200,
      parity: "N",
      stop_bits: 1,
      byte_size: 8,
      timeout_seconds: 0.5,
      retries: 1,
      poll_interval_seconds: 15,
      inter_request_delay_ms: 20,
      retry_delay_ms: 40,
      float_endian: ">",
    };
  } else {
    connectionSettings = {
      port: result.port,
      slave_id: result.unit_id,
      baud_rate: 9600,
      parity: "N",
      stop_bits: 1,
      byte_size: 8,
      timeout_seconds: 5,
      retries: 3,
      poll_interval_seconds: 15,
    };
  }

  return {
    name:
      exactCandidate != null
        ? `${exactCandidate.model} ${result.unit_id}`
        : `Nodo seriale ${result.unit_id}`,
    brand,
    model,
    protocol,
    transport: "serial",
    connectionSettings,
    sourceLabel: `RS485 | ${getSerialPortDisplayName(result.port)} | unit ${result.unit_id}`,
    candidateProfiles: candidates,
    candidateProfileCount: result.candidate_profile_count,
  };
}

function buildTcpPrefill(result: DeviceDiscoveryTcpResult): DeviceDiscoveryPrefill {
  const candidates = result.candidate_profiles;
  const uniqueBrands = Array.from(new Set(candidates.map((candidate) => candidate.brand)));
  const uniqueProtocols = Array.from(new Set(candidates.map((candidate) => candidate.protocol)));
  const exactCandidate = candidates.length === 1 ? candidates[0] : null;
  const protocol = exactCandidate?.protocol ?? uniqueProtocols[0] ?? "modbus_tcp";
  const brand = exactCandidate?.brand ?? (uniqueBrands.length === 1 ? uniqueBrands[0] : "");
  const model = exactCandidate?.model ?? "";

  return {
    name:
      exactCandidate != null
        ? `${exactCandidate.model} ${result.host}`
        : `Nodo rete ${result.host}:${result.unit_id}`,
    brand,
    model,
    protocol,
    transport: "tcp",
    connectionSettings: {
      host: result.host,
      port: result.port,
      unit_id: result.unit_id,
      timeout_seconds: 5,
      retries: 3,
      poll_interval_seconds: 15,
    },
    sourceLabel: `TCP | ${result.host}:${result.port} | unit ${result.unit_id}`,
    candidateProfiles: candidates,
    candidateProfileCount: result.candidate_profile_count,
  };
}

export function DeviceDiscoveryModal({
  open,
  onClose,
  existingDevices,
  onBrowsingStateChange,
  onResultCountChange,
  onSelectResult,
}: DeviceDiscoveryModalProps) {
  const [serialPorts, setSerialPorts] = useState<SerialPortInfo[]>([]);
  const [networkInterfaces, setNetworkInterfaces] = useState<NetworkInterfaceInfo[]>([]);
  const [activeTab, setActiveTab] = useState<DiscoveryTab>("serial");
  const [serialForm, setSerialForm] = useState<SerialDiscoveryForm>(SERIAL_DEFAULTS);
  const [tcpForm, setTcpForm] = useState<TcpDiscoveryForm>(TCP_DEFAULTS);
  const [serialResults, setSerialResults] = useState<DeviceDiscoveryRtuResult[]>([]);
  const [tcpResults, setTcpResults] = useState<DeviceDiscoveryTcpResult[]>([]);
  const [serialSummary, setSerialSummary] = useState<{ requestCount: number; durationMs: number } | null>(
    null,
  );
  const [tcpSummary, setTcpSummary] = useState<{ requestCount: number; durationMs: number } | null>(null);
  const [runningTab, setRunningTab] = useState<DiscoveryTab | null>(null);
  const [protocolOperationState, setProtocolOperationState] = useState<ProtocolOperationState | null>(null);
  const [activeFilter, setActiveFilter] = useState<DiscoveryFilter>("all");
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const browseAbortControllerRef = useRef<AbortController | null>(null);
  const activeBrowseOperationIdRef = useRef<string | null>(null);

  const resultCount = serialResults.length + tcpResults.length;

  useEffect(() => {
    let isActive = true;

    async function loadOptions() {
      setLoadingOptions(true);
      setLoadError(null);
      try {
        const [nextSerialPorts, nextNetworkInterfaces] = await Promise.all([
          getSerialPorts(),
          getNetworkInterfaces(),
        ]);
        if (!isActive) {
          return;
        }
        setSerialPorts(nextSerialPorts.ports);
        setNetworkInterfaces(nextNetworkInterfaces.interfaces);
        const defaultPort = nextSerialPorts.ports[0]?.name ?? "";
        const defaultInterface = pickDefaultInterface(nextNetworkInterfaces.interfaces);
        const defaultRange = defaultInterface ? buildHostSelectionRange(defaultInterface.address) : null;
        setSerialForm((current) => ({
          ...current,
          port: current.port || defaultPort,
        }));
        setTcpForm((current) => ({
          ...current,
          interfaceAddress: current.interfaceAddress || defaultInterface?.address || "",
          hostStart: current.hostStart || defaultRange?.start || "",
          hostEnd: current.hostEnd || defaultRange?.end || "",
        }));
      } catch (error) {
        if (!isActive) {
          return;
        }
        setLoadError(
          error instanceof Error ? error.message : "Impossibile caricare le opzioni di browsing.",
        );
      } finally {
        if (isActive) {
          setLoadingOptions(false);
        }
      }
    }

    void loadOptions();
    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    onBrowsingStateChange(runningTab !== null || protocolOperationState?.active === true);
  }, [onBrowsingStateChange, protocolOperationState?.active, runningTab]);

  useEffect(() => {
    if (open) {
      return;
    }
    const operationId = activeBrowseOperationIdRef.current;
    if (operationId) {
      void cancelProtocolOperation({
        operation_id: operationId,
        reason: "modal_closed",
      }).catch(() => undefined);
      activeBrowseOperationIdRef.current = null;
    }
    browseAbortControllerRef.current?.abort();
    browseAbortControllerRef.current = null;
    setRunningTab(null);
  }, [open]);

  useEffect(
    () => () => {
      const operationId = activeBrowseOperationIdRef.current;
      if (operationId) {
        void cancelProtocolOperation({
          operation_id: operationId,
          reason: "modal_unmounted",
        }).catch(() => undefined);
        activeBrowseOperationIdRef.current = null;
      }
      browseAbortControllerRef.current?.abort();
      browseAbortControllerRef.current = null;
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
        if (isActive) {
          setProtocolOperationState(state);
        }
      } catch {
        if (isActive) {
          setProtocolOperationState(null);
        }
      }
    }

    void refreshOperationState();
    const intervalId = window.setInterval(refreshOperationState, runningTab ? 1000 : 2500);
    return () => {
      isActive = false;
      window.clearInterval(intervalId);
    };
  }, [open, runningTab]);

  useEffect(() => {
    onResultCountChange(resultCount);
  }, [onResultCountChange, resultCount]);

  const networkInterfaceOptions = useMemo(
    () =>
      networkInterfaces.map((networkInterface) => ({
        value: networkInterface.address,
        label: `${networkInterface.name} | ${networkInterface.address}`,
      })),
    [networkInterfaces],
  );

  const decoratedSerialResults = useMemo(
    () =>
      sortDecoratedDiscoveryItems(
        serialResults.map((result) => ({
          kind: "serial" as const,
          result,
          existingDevice: matchExistingSerialDevice(result, existingDevices),
        })),
      ),
    [existingDevices, serialResults],
  );

  const decoratedTcpResults = useMemo(
    () =>
      sortDecoratedDiscoveryItems(
        tcpResults.map((result) => ({
          kind: "tcp" as const,
          result,
          existingDevice: matchExistingTcpDevice(result, existingDevices),
        })),
      ),
    [existingDevices, tcpResults],
  );

  const filteredSerialResults = useMemo(
    () => filterDiscoveryItems(decoratedSerialResults, activeFilter),
    [activeFilter, decoratedSerialResults],
  );
  const filteredTcpResults = useMemo(
    () => filterDiscoveryItems(decoratedTcpResults, activeFilter),
    [activeFilter, decoratedTcpResults],
  );
  const activeDecoratedCount =
    activeTab === "serial" ? decoratedSerialResults.length : decoratedTcpResults.length;
  const activeNewCount =
    activeTab === "serial"
      ? decoratedSerialResults.filter((item) => item.existingDevice === null).length
      : decoratedTcpResults.filter((item) => item.existingDevice === null).length;
  const activeConfiguredCount = activeDecoratedCount - activeNewCount;
  const activeConfiguredOfflineCount =
    activeTab === "serial"
      ? decoratedSerialResults.filter((item) => item.existingDevice !== null && isExistingDeviceOffline(item.existingDevice)).length
      : decoratedTcpResults.filter((item) => item.existingDevice !== null && isExistingDeviceOffline(item.existingDevice)).length;
  const filteredSerialGroups = useMemo(
    () => buildDiscoveryGroups(filteredSerialResults),
    [filteredSerialResults],
  );
  const filteredTcpGroups = useMemo(() => buildDiscoveryGroups(filteredTcpResults), [filteredTcpResults]);

  function handleSerialFieldChange<Key extends keyof SerialDiscoveryForm>(
    key: Key,
    value: SerialDiscoveryForm[Key],
  ) {
    setScanError(null);
    setSerialForm((current) => ({ ...current, [key]: value }));
  }

  function handleSerialProtocolChange(scanProtocol: RtuDiscoveryProtocol) {
    setScanError(null);
    setSerialResults([]);
    setSerialSummary(null);
    setSerialForm((current) => applySerialDiscoveryPreset(current, scanProtocol));
  }

  function handleTcpFieldChange<Key extends keyof TcpDiscoveryForm>(
    key: Key,
    value: TcpDiscoveryForm[Key],
  ) {
    setScanError(null);
    setTcpForm((current) => ({ ...current, [key]: value }));
  }

  function handleInterfaceSelection(address: string) {
    setScanError(null);
    const range = buildHostSelectionRange(address);
    setTcpForm((current) => ({
      ...current,
      interfaceAddress: address,
      hostStart: range?.start ?? current.hostStart,
      hostEnd: range?.end ?? current.hostEnd,
    }));
  }

  function handleCloseRequest() {
    if (runningTab !== null || protocolOperationState?.active) {
      setScanError("Ferma il browsing in corso o attendi la fine prima di chiudere questa pagina.");
      return;
    }
    onClose();
  }

  async function handleStopBrowsing() {
    const operationId = activeBrowseOperationIdRef.current ?? protocolOperationState?.operation_id ?? null;
    try {
      const state = await cancelProtocolOperation({
        operation_id: operationId,
        reason: "operator_stop",
      });
      setProtocolOperationState(state);
    } catch (error) {
      setScanError(error instanceof Error ? error.message : "Impossibile fermare il browsing in corso.");
    }
    browseAbortControllerRef.current?.abort();
  }

  async function handleBrowseSerial() {
    setScanError(null);
    const remoteOperationState = await getProtocolOperationState().catch(() => null);
    if (remoteOperationState?.active) {
      setProtocolOperationState(remoteOperationState);
      setScanError(
        `${describeDiscoveryOperation(remoteOperationState) ?? "Un'altra operazione protocollo e gia in corso."} Ferma o attendi la fine prima di avviare un nuovo browsing.`,
      );
      return;
    }
    setRunningTab("serial");
    const controller = new AbortController();
    const operationId = createDiscoveryOperationId();
    browseAbortControllerRef.current = controller;
    activeBrowseOperationIdRef.current = operationId;
    try {
      if (!serialForm.port.trim()) {
        throw new Error("Seleziona prima una porta seriale.");
      }
      const slaveIds = buildIntegerRange(serialForm.slaveIdStart, serialForm.slaveIdEnd, 0, 247);
      const response = await discoverRtuDevices({
        operation_id: operationId,
        operation_label: `Browsing RTU ${getSerialPortDisplayName(serialForm.port.trim())}`,
        port: serialForm.port.trim(),
        baud_rate: Number(serialForm.baudRate),
        parity: serialForm.parity,
        stop_bits: Number(serialForm.stopBits),
        byte_size: Number(serialForm.byteSize),
        timeout_seconds: Number(serialForm.timeoutSeconds),
        retries: Number(serialForm.retries),
        scan_protocol: serialForm.scanProtocol,
        slave_ids: slaveIds,
      }, { signal: controller.signal });
      setSerialResults(response.results);
      setSerialSummary({
        requestCount: response.request_count,
        durationMs: response.duration_ms,
      });
      setActiveTab("serial");
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Browsing seriale non riuscito.";
      setScanError(
        controller.signal.aborted
          ? "Browsing seriale interrotto dall'operatore."
          : errorMessage,
      );
    } finally {
      if (activeBrowseOperationIdRef.current === operationId) {
        try {
          const state = await finishProtocolOperation({ operation_id: operationId });
          setProtocolOperationState(state);
        } catch {
          // The next polling tick will refresh the operation state.
        }
        activeBrowseOperationIdRef.current = null;
      }
      if (browseAbortControllerRef.current === controller) {
        browseAbortControllerRef.current = null;
      }
      setRunningTab((current) => (current === "serial" ? null : current));
    }
  }

  async function handleBrowseTcp() {
    setScanError(null);
    const remoteOperationState = await getProtocolOperationState().catch(() => null);
    if (remoteOperationState?.active) {
      setProtocolOperationState(remoteOperationState);
      setScanError(
        `${describeDiscoveryOperation(remoteOperationState) ?? "Un'altra operazione protocollo e gia in corso."} Ferma o attendi la fine prima di avviare un nuovo browsing.`,
      );
      return;
    }
    setRunningTab("tcp");
    const controller = new AbortController();
    const operationId = createDiscoveryOperationId();
    browseAbortControllerRef.current = controller;
    activeBrowseOperationIdRef.current = operationId;
    try {
      const unitIds = buildIntegerRange(tcpForm.unitIdStart, tcpForm.unitIdEnd, 0, 247);
      const portStart = Number(tcpForm.portStart);
      const portEnd = Number(tcpForm.portEnd);
      if (!Number.isInteger(portStart) || !Number.isInteger(portEnd)) {
        throw new Error("Definisci un intervallo porte valido per il browsing TCP.");
      }
      if (!tcpForm.hostStart.trim() || !tcpForm.hostEnd.trim()) {
        throw new Error("Definisci un intervallo IP valido per il browsing TCP.");
      }
      const startParts = tcpForm.hostStart.trim().split(".");
      const endParts = tcpForm.hostEnd.trim().split(".");
      if (startParts.length !== 4 || endParts.length !== 4) {
        throw new Error("Inserisci un intervallo IP valido per il browsing TCP.");
      }
      const hostCount = Number(endParts[3]) - Number(startParts[3]) + 1;
      const portCount = portEnd - portStart + 1;
      const endpointCount = hostCount * portCount * unitIds.length;
      if (endpointCount > 512) {
        throw new Error(
          `Intervallo troppo ampio per il browsing TCP: ${endpointCount} endpoint da sondare.`,
        );
      }
      const response = await discoverTcpDevices({
        operation_id: operationId,
        operation_label: `Browsing TCP ${tcpForm.hostStart.trim()}:${portStart}-${portEnd}`,
        host_start: tcpForm.hostStart.trim(),
        host_end: tcpForm.hostEnd.trim(),
        port_start: portStart,
        port_end: portEnd,
        timeout_seconds: Number(tcpForm.timeoutSeconds),
        retries: Number(tcpForm.retries),
        unit_ids: unitIds,
      }, { signal: controller.signal });
      setTcpResults(response.results);
      setTcpSummary({
        requestCount: response.request_count,
        durationMs: response.duration_ms,
      });
      setActiveTab("tcp");
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Browsing TCP non riuscito.";
      setScanError(
        controller.signal.aborted ? "Browsing TCP interrotto dall'operatore." : errorMessage,
      );
    } finally {
      if (activeBrowseOperationIdRef.current === operationId) {
        try {
          const state = await finishProtocolOperation({ operation_id: operationId });
          setProtocolOperationState(state);
        } catch {
          // The next polling tick will refresh the operation state.
        }
        activeBrowseOperationIdRef.current = null;
      }
      if (browseAbortControllerRef.current === controller) {
        browseAbortControllerRef.current = null;
      }
      setRunningTab((current) => (current === "tcp" ? null : current));
    }
  }

  const activeSummary = activeTab === "serial" ? serialSummary : tcpSummary;
  const currentSerialPreset = SERIAL_DISCOVERY_PRESETS[serialForm.scanProtocol];
  const activeOperationDescription = describeDiscoveryOperation(protocolOperationState);
  const operationBlocksBrowsing = runningTab === null && protocolOperationState?.active === true;

  return (
    <div
      className={`device-discovery-shell ${open ? "device-discovery-shell--open" : ""}`}
      aria-hidden={!open}
    >
      <div className="modal-backdrop" role="presentation" onClick={handleCloseRequest}>
        <aside
          className="modal-panel modal-panel--wide device-discovery-panel"
          aria-label="Browsing dispositivi"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="modal-header">
            <div>
              <p className="panel-kicker">Browsing dispositivi</p>
              <h2>Ricerca nodi RS485 e TCP</h2>
              <p className="field-note">
                Trova i nodi che rispondono e associali dopo al modello inverter corretto.
              </p>
            </div>
            <button className="icon-button" type="button" onClick={handleCloseRequest}>
              Chiudi
            </button>
          </div>

          <div className="modal-body">
            {loadingOptions ? (
              <div className="panel-state">Caricamento opzioni di browsing...</div>
            ) : null}
            {loadError ? (
              <div className="panel-state panel-state--error" role="alert">
                {loadError}
              </div>
            ) : null}

            <div className="device-discovery-tabs" role="tablist" aria-label="Modalita browsing">
              <button
                className={`device-discovery-tab ${
                  activeTab === "serial" ? "device-discovery-tab--active" : ""
                }`}
                type="button"
                role="tab"
                aria-selected={activeTab === "serial"}
                onClick={() => setActiveTab("serial")}
              >
                RS485
                {serialResults.length > 0 ? <span>{serialResults.length}</span> : null}
              </button>
              <button
                className={`device-discovery-tab ${
                  activeTab === "tcp" ? "device-discovery-tab--active" : ""
                }`}
                type="button"
                role="tab"
                aria-selected={activeTab === "tcp"}
                onClick={() => setActiveTab("tcp")}
              >
                TCP
                {tcpResults.length > 0 ? <span>{tcpResults.length}</span> : null}
              </button>
            </div>

            {scanError ? (
              <div className="panel-state panel-state--error" role="alert">
                {scanError}
              </div>
            ) : null}

            {activeTab === "serial" ? (
              <section className="discovery-panel">
                <div className="discovery-panel-header">
                  <div>
                    <h3>{currentSerialPreset.title}</h3>
                    <p className="discovery-panel-copy">{currentSerialPreset.copy}</p>
                  </div>
                  <div className="discovery-panel-meta">
                    <strong>Modalita RS485</strong>
                    <span>{currentSerialPreset.label}</span>
                    <span>
                      Da {serialForm.slaveIdStart} a {serialForm.slaveIdEnd}
                    </span>
                  </div>
                </div>

                <div className="discovery-grid">
                  <label className="field">
                    <span className="field-label">Modalita browsing</span>
                    <select
                      className="field-control"
                      value={serialForm.scanProtocol}
                      onChange={(event) =>
                        handleSerialProtocolChange(event.currentTarget.value as RtuDiscoveryProtocol)
                      }
                      disabled={runningTab !== null}
                    >
                      {SERIAL_DISCOVERY_PROTOCOL_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">Porta seriale</span>
                    <select
                      className="field-control"
                      value={serialForm.port}
                      onChange={(event) => handleSerialFieldChange("port", event.currentTarget.value)}
                      disabled={runningTab !== null}
                    >
                      <option value="">Seleziona porta</option>
                      {serialPorts.map((serialPort) => (
                        <option key={serialPort.name} value={serialPort.name}>
                          {buildSerialPortLabel(serialPort)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">Baud rate</span>
                    <input
                      className="field-control"
                      type="number"
                      value={serialForm.baudRate}
                      onChange={(event) =>
                        handleSerialFieldChange("baudRate", event.currentTarget.value)
                      }
                      disabled={runningTab !== null}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Parita</span>
                    <select
                      className="field-control"
                      value={serialForm.parity}
                      onChange={(event) => handleSerialFieldChange("parity", event.currentTarget.value)}
                      disabled={runningTab !== null}
                    >
                      {PARITY_OPTIONS.map((parity) => (
                        <option key={parity} value={parity}>
                          {parity}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">Stop bit</span>
                    <select
                      className="field-control"
                      value={serialForm.stopBits}
                      onChange={(event) =>
                        handleSerialFieldChange("stopBits", event.currentTarget.value)
                      }
                      disabled={runningTab !== null}
                    >
                      <option value="1">1</option>
                      <option value="2">2</option>
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">Timeout connessione (s)</span>
                    <input
                      className="field-control"
                      type="number"
                      min={0.05}
                      step={0.05}
                      value={serialForm.timeoutSeconds}
                      onChange={(event) =>
                        handleSerialFieldChange("timeoutSeconds", event.currentTarget.value)
                      }
                      disabled={runningTab !== null}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Da unit ID</span>
                    <input
                      className="field-control"
                      type="number"
                      value={serialForm.slaveIdStart}
                      onChange={(event) =>
                        handleSerialFieldChange("slaveIdStart", event.currentTarget.value)
                      }
                      disabled={runningTab !== null}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">A unit ID</span>
                    <input
                      className="field-control"
                      type="number"
                      value={serialForm.slaveIdEnd}
                      onChange={(event) =>
                        handleSerialFieldChange("slaveIdEnd", event.currentTarget.value)
                      }
                      disabled={runningTab !== null}
                    />
                  </label>
                </div>

                <div className="discovery-panel-actions">
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={handleBrowseSerial}
                    disabled={loadingOptions || runningTab !== null || operationBlocksBrowsing}
                  >
                    {runningTab === "serial"
                      ? `${currentSerialPreset.actionLabel} in corso...`
                      : operationBlocksBrowsing
                        ? "Browsing gia in corso"
                      : currentSerialPreset.actionLabel}
                  </button>
                  {runningTab === "serial" || operationBlocksBrowsing ? (
                    <button
                      className="chip-inline-button"
                      type="button"
                      onClick={() => void handleStopBrowsing()}
                    >
                      Interrompi browsing
                    </button>
                  ) : null}
                  <span className="field-note">
                    {currentSerialPreset.note}
                  </span>
                  <span className="field-note">
                    Puoi fermare il browsing in corso con il pulsante di stop.
                  </span>
                  {activeOperationDescription ? (
                    <span className="field-note">{activeOperationDescription}</span>
                  ) : null}
                </div>
              </section>
            ) : (
              <section className="discovery-panel">
                <div className="discovery-panel-header">
                  <div>
                    <h3>Browsing Ethernet / Modbus TCP</h3>
                    <p className="discovery-panel-copy">
                      Scansione su range IP, porte e unit ID per trovare i nodi che rispondono in
                      rete.
                    </p>
                  </div>
                  <div className="discovery-panel-meta">
                    <strong>Scope di rete</strong>
                              <span>
                      {tcpForm.hostStart || "--"} {"->"} {tcpForm.hostEnd || "--"}
                    </span>
                  </div>
                </div>

                <div className="discovery-grid">
                  <label className="field">
                    <span className="field-label">Scheda di rete</span>
                    <select
                      className="field-control"
                      value={tcpForm.interfaceAddress}
                      onChange={(event) => handleInterfaceSelection(event.currentTarget.value)}
                      disabled={runningTab !== null}
                    >
                      <option value="">Seleziona interfaccia</option>
                      {networkInterfaceOptions.map((networkInterface) => (
                        <option key={networkInterface.value} value={networkInterface.value}>
                          {networkInterface.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">IP iniziale</span>
                    <input
                      className="field-control"
                      type="text"
                      value={tcpForm.hostStart}
                      onChange={(event) => handleTcpFieldChange("hostStart", event.currentTarget.value)}
                      disabled={runningTab !== null}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">IP finale</span>
                    <input
                      className="field-control"
                      type="text"
                      value={tcpForm.hostEnd}
                      onChange={(event) => handleTcpFieldChange("hostEnd", event.currentTarget.value)}
                      disabled={runningTab !== null}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Porta iniziale</span>
                    <input
                      className="field-control"
                      type="number"
                      value={tcpForm.portStart}
                      onChange={(event) =>
                        handleTcpFieldChange("portStart", event.currentTarget.value)
                      }
                      disabled={runningTab !== null}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Porta finale</span>
                    <input
                      className="field-control"
                      type="number"
                      value={tcpForm.portEnd}
                      onChange={(event) => handleTcpFieldChange("portEnd", event.currentTarget.value)}
                      disabled={runningTab !== null}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Timeout connessione (s)</span>
                    <input
                      className="field-control"
                      type="number"
                      min={0.05}
                      step={0.05}
                      value={tcpForm.timeoutSeconds}
                      onChange={(event) =>
                        handleTcpFieldChange("timeoutSeconds", event.currentTarget.value)
                      }
                      disabled={runningTab !== null}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Da unit ID</span>
                    <input
                      className="field-control"
                      type="number"
                      value={tcpForm.unitIdStart}
                      onChange={(event) =>
                        handleTcpFieldChange("unitIdStart", event.currentTarget.value)
                      }
                      disabled={runningTab !== null}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">A unit ID</span>
                    <input
                      className="field-control"
                      type="number"
                      value={tcpForm.unitIdEnd}
                      onChange={(event) =>
                        handleTcpFieldChange("unitIdEnd", event.currentTarget.value)
                      }
                      disabled={runningTab !== null}
                    />
                  </label>
                </div>

                <div className="discovery-panel-actions">
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={handleBrowseTcp}
                    disabled={loadingOptions || runningTab !== null || operationBlocksBrowsing}
                  >
                    {runningTab === "tcp"
                      ? "Browsing TCP in corso..."
                      : operationBlocksBrowsing
                        ? "Browsing gia in corso"
                        : "Avvia browsing TCP"}
                  </button>
                  {runningTab === "tcp" || operationBlocksBrowsing ? (
                    <button
                      className="chip-inline-button"
                      type="button"
                      onClick={() => void handleStopBrowsing()}
                    >
                      Interrompi browsing
                    </button>
                  ) : null}
                  <span className="field-note">
                    Parti con range stretti e allargali progressivamente.
                  </span>
                  {activeOperationDescription ? (
                    <span className="field-note">{activeOperationDescription}</span>
                  ) : null}
                </div>
              </section>
            )}

            <section className="discovery-panel discovery-panel--results">
              <div className="discovery-panel-header">
                <div>
                  <h3>Dispositivi trovati</h3>
                  <p className="discovery-panel-copy">
                    Dal browsing alla configurazione: prima individua i nodi nuovi, poi
                    precompila il modello piu probabile e completa l'aggiunta in dashboard.
                  </p>
                </div>
                <div className="discovery-panel-meta">
                  <strong>{activeDecoratedCount} nodi</strong>
                              <span>
                    {activeSummary
                      ? `${activeSummary.requestCount} probe in ${activeSummary.durationMs} ms`
                      : "Nessuna scansione completata su questa vista."}
                  </span>
                </div>
              </div>

              {activeDecoratedCount > 0 ? (
                <>
                  <div className="discovery-guidance-strip">
                    <strong>Percorso consigliato</strong>
                              <span>1. individua i nodi nuovi</span>
                    <span>2. apri il form con il nodo precompilato</span>
                    <span>3. scegli il modello suggerito</span>
                    <span>4. testa la connessione e salva</span>
                  </div>
                  <div className="discovery-results-toolbar">
                    <div className="discovery-results-summary">
                      <span className="discovery-summary-pill">Nuovi {activeNewCount}</span>
                      <span className="discovery-summary-pill discovery-summary-pill--muted">
                        Gia configurati {activeConfiguredCount}
                      </span>
                      {activeConfiguredOfflineCount > 0 ? (
                        <span className="discovery-summary-pill discovery-summary-pill--attention">
                          Gia presenti offline {activeConfiguredOfflineCount}
                        </span>
                      ) : null}
                    </div>
                    <div className="discovery-filter-tabs" role="tablist" aria-label="Filtro risultati">
                      <button
                        className={`discovery-filter-tab ${
                          activeFilter === "all" ? "discovery-filter-tab--active" : ""
                        }`}
                        type="button"
                        onClick={() => setActiveFilter("all")}
                      >
                        Tutti
                      </button>
                      <button
                        className={`discovery-filter-tab ${
                          activeFilter === "new" ? "discovery-filter-tab--active" : ""
                        }`}
                        type="button"
                        onClick={() => setActiveFilter("new")}
                      >
                        Solo nuovi
                      </button>
                      <button
                        className={`discovery-filter-tab ${
                          activeFilter === "configured" ? "discovery-filter-tab--active" : ""
                        }`}
                        type="button"
                        onClick={() => setActiveFilter("configured")}
                      >
                        Gia presenti
                      </button>
                    </div>
                  </div>
                  <div className="discovery-results">
                    {(activeTab === "serial" ? filteredSerialGroups.length : filteredTcpGroups.length) > 0 ? (
                      (activeTab === "serial" ? filteredSerialGroups : filteredTcpGroups).map((group) => (
                        <section key={group.key} className="discovery-group">
                          <div className="discovery-group-header">
                            <div>
                              <strong>{group.label}</strong>
                              <span>
                                {group.items.length} nodi | nuovi {group.newCount} | gia configurati {group.configuredCount}
                              </span>
                            </div>
                            {group.configuredOfflineCount > 0 ? (
                              <span className="discovery-group-alert">
                                {group.configuredOfflineCount} gia presenti offline
                              </span>
                            ) : null}
                          </div>
                          <div className="discovery-group-results">
                            {group.items.map((item) => {
                              const result = item.result;
                              const candidates = result.candidate_profiles;
                              const isConfigured = item.existingDevice !== null;
                              const configuredStatusLabel = formatExistingDevicePresence(item.existingDevice);
                              const discoverySignature = describeDiscoverySignature(
                                result.candidate_profile_count,
                              );
                              const resultKey =
                                item.kind === "serial"
                                  ? `${result.port}-${result.unit_id}`
                                  : `${(result as DeviceDiscoveryTcpResult).host}-${result.port}-${result.unit_id}`;
                              const endpointLabel =
                                item.kind === "serial"
                                  ? `RS485 | ${getSerialPortDisplayName((result as DeviceDiscoveryRtuResult).port)} | unit ${result.unit_id}`
                                  : `TCP | ${(result as DeviceDiscoveryTcpResult).host}:${result.port} | unit ${result.unit_id}`;
                              return (
                                <article
                                  key={resultKey}
                                  className={`discovery-match-card discovery-match-card--rich ${
                                    isConfigured
                                      ? isExistingDeviceOffline(item.existingDevice)
                                        ? "discovery-match-card--attention"
                                        : "discovery-match-card--configured"
                                      : "discovery-match-card--new"
                                  }`}
                                >
                                  <div className="discovery-match-copy">
                                    <div className="discovery-match-topline">
                                      <strong>{endpointLabel}</strong>
                                      <div className="discovery-match-badges">
                                        <span
                                          className={`discovery-status-badge ${
                                            isConfigured
                                              ? isExistingDeviceOffline(item.existingDevice)
                                                ? "discovery-status-badge--attention"
                                                : "discovery-status-badge--configured"
                                              : "discovery-status-badge--new"
                                          }`}
                                        >
                                          {isConfigured ? configuredStatusLabel : "Nuovo nodo"}
                                        </span>
                                        <span
                                          className={`discovery-status-badge discovery-status-badge--signature discovery-status-badge--${discoverySignature.tone}`}
                                        >
                                          {discoverySignature.label}
                                        </span>
                                      </div>
                                    </div>
                                    <span>{formatCandidateHeadline(candidates)}</span>
                                    <span>
                                      {formatCandidateCount(candidates)}
                                      {result.candidate_profile_count > candidates.length
                                        ? ` | anteprima ${candidates.length}/${result.candidate_profile_count}`
                                        : ""}
                                    </span>
                                    <span className="discovery-recommended-action">
                                      {formatRecommendedAction(isConfigured, result.candidate_profile_count)}
                                    </span>
                                    <span>{formatDiscoverySignatureLine(candidates, result)}</span>
                                    <span>Valori letti: {formatScanRawValues(result.raw_values)}</span>
                                    {item.existingDevice ? (
                                      <span>
                                        Presente come {item.existingDevice.name} | {item.existingDevice.brand} |{" "}
                                        {item.existingDevice.model}
                                      </span>
                                    ) : null}
                                  </div>
                                  <div className="discovery-match-actions">
                                    <div className="discovery-brand-list">
                                      {topCandidateLabels(candidates).map((label) => (
                                        <span key={label} className="sidebar-overview-chip">
                                          {label}
                                        </span>
                                      ))}
                                    </div>
                                    <button
                                      className={isConfigured ? "secondary-button" : "action-button"}
                                      type="button"
                                      disabled={isConfigured}
                                      onClick={() =>
                                        onSelectResult(
                                          item.kind === "serial"
                                            ? buildSerialPrefill(result as DeviceDiscoveryRtuResult)
                                            : buildTcpPrefill(result as DeviceDiscoveryTcpResult),
                                        )
                                      }
                                    >
                                      {isConfigured
                                        ? "Gia configurato"
                                        : candidates.length === 1
                                          ? "Precompila aggiunta"
                                          : "Apri e scegli modello"}
                                    </button>
                                  </div>
                                </article>
                              );
                            })}
                          </div>
                        </section>
                      ))
                    ) : (
                      <div className="discovery-empty">
                        Nessun nodo corrisponde al filtro attuale. Prova a mostrare tutti i risultati
                        o solo i nodi nuovi.
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="discovery-empty">
                  {runningTab === activeTab
                    ? "Browsing in corso su questa vista..."
                    : "Nessun nodo trovato ancora per questa modalita."}
                </div>
              )}
            </section>
          </div>
        </aside>
      </div>
    </div>
  );
}
