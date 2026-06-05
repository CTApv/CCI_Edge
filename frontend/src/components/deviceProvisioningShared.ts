import type {
  CatalogModel,
  ConnectionSettings,
  CreateDevicePayload,
  Device,
  ProtocolTestPayload,
  ProtocolTestResult,
  SerialPortInfo,
  UpdateDevicePayload,
} from "../api";

export type GuidedFieldOption = {
  value: string;
  label: string;
};

export type GuidedFieldConfig = {
  key: string;
  label: string;
  type: "text" | "number";
  aliases?: string[];
  options?: GuidedFieldOption[];
};

const SERIAL_PORT_DISPLAY_NAMES: Record<string, string> = {
  "/dev/ttyUSB0": "COM1-RS485",
  "/dev/ttyUSB1": "COM2-USB",
};

export type ProvisionFormState = {
  name: string;
  brand: string;
  model: string;
  protocol: string;
  transport: string;
  status: string;
  connectionSettingsText: string;
};

export const EMPTY_PROVISION_FORM: ProvisionFormState = {
  name: "",
  brand: "",
  model: "",
  protocol: "",
  transport: "",
  status: "pending",
  connectionSettingsText: "{}",
};

export const PROTOCOL_TRANSPORTS: Record<string, string> = {
  modbus_tcp: "tcp",
  modbus_rtu: "serial",
  aurora: "serial",
  sunspec: "tcp",
  delta_rs485: "serial",
};

export const PROTOCOL_ALLOWED_TRANSPORTS: Record<string, string[]> = {
  modbus_tcp: ["tcp"],
  modbus_rtu: ["serial", "tcp"],
  aurora: ["serial"],
  sunspec: ["tcp"],
  delta_rs485: ["serial"],
};

export const PROTOCOL_DEFAULT_SETTINGS: Record<string, ConnectionSettings> = {
  modbus_tcp: {
    host: "192.168.1.100",
    port: 502,
    unit_id: 1,
    timeout_seconds: 5,
    retries: 3,
    poll_interval_seconds: 15,
  },
  modbus_rtu: {
    port: "COM1",
    slave_id: 1,
    baud_rate: 9600,
    parity: "N",
    stop_bits: 1,
    byte_size: 8,
    timeout_seconds: 5,
    retries: 3,
    poll_interval_seconds: 15,
  },
  aurora: {
    port: "COM1",
    address: 2,
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
  },
  delta_rs485: {
    port: "COM1",
    address: 1,
    baud_rate: 19200,
    parity: "N",
    stop_bits: 1,
    byte_size: 8,
    timeout_seconds: 1,
    retries: 1,
    poll_interval_seconds: 15,
    inter_request_delay_ms: 10,
    retry_delay_ms: 50,
    delta_variant: 1,
  },
  sunspec: {
    host: "192.168.1.101",
    port: 502,
    unit_id: 126,
    timeout_seconds: 5,
    retries: 3,
    poll_interval_seconds: 15,
  },
};

const PROTOCOL_TRANSPORT_DEFAULT_SETTINGS: Record<string, ConnectionSettings> = {
  "modbus_rtu:tcp": {
    host: "192.168.1.100",
    port: 502,
    unit_id: 1,
    timeout_seconds: 5,
    retries: 3,
    poll_interval_seconds: 15,
  },
};

const PARITY_OPTIONS: GuidedFieldOption[] = [
  { value: "N", label: "N" },
  { value: "E", label: "E" },
  { value: "O", label: "O" },
];

export const GUIDED_CONNECTION_FIELDS: Record<string, GuidedFieldConfig[]> = {
  modbus_tcp: [
    { key: "host", label: "Indirizzo host", type: "text" },
    { key: "port", label: "Porta TCP", type: "number" },
    { key: "unit_id", label: "ID unita", type: "number", aliases: ["slave_id"] },
  ],
  modbus_rtu: [
    { key: "port", label: "Porta seriale", type: "text" },
    { key: "slave_id", label: "ID slave", type: "number" },
    { key: "baud_rate", label: "Velocita baud", type: "number" },
    { key: "parity", label: "Parita", type: "text", options: PARITY_OPTIONS },
    {
      key: "stop_bits",
      label: "Bit di stop",
      type: "number",
      options: [
        { value: "1", label: "1" },
        { value: "2", label: "2" },
      ],
    },
    {
      key: "byte_size",
      label: "Dimensione byte",
      type: "number",
      options: [
        { value: "7", label: "7" },
        { value: "8", label: "8" },
      ],
    },
    { key: "timeout_seconds", label: "Timeout connessione (s)", type: "number" },
  ],
  aurora: [
    { key: "port", label: "Porta seriale", type: "text" },
    { key: "address", label: "Indirizzo", type: "number" },
    { key: "baud_rate", label: "Velocita baud", type: "number" },
    { key: "parity", label: "Parita", type: "text", options: PARITY_OPTIONS },
    { key: "timeout_seconds", label: "Timeout connessione (s)", type: "number" },
  ],
  delta_rs485: [
    { key: "port", label: "Porta seriale", type: "text" },
    { key: "address", label: "Indirizzo", type: "number" },
    { key: "baud_rate", label: "Velocita baud", type: "number" },
    { key: "parity", label: "Parita", type: "text", options: PARITY_OPTIONS },
    {
      key: "stop_bits",
      label: "Bit di stop",
      type: "number",
      options: [
        { value: "1", label: "1" },
        { value: "2", label: "2" },
      ],
    },
    {
      key: "byte_size",
      label: "Dimensione byte",
      type: "number",
      options: [
        { value: "7", label: "7" },
        { value: "8", label: "8" },
      ],
    },
    {
      key: "delta_variant",
      label: "Variante Delta",
      type: "number",
      options: [
        { value: "1", label: "SI 2500" },
        { value: "3", label: "SI 3300" },
        { value: "4", label: "SI 5000" },
      ],
    },
    { key: "timeout_seconds", label: "Timeout connessione (s)", type: "number" },
  ],
  sunspec: [
    { key: "host", label: "Indirizzo host", type: "text" },
    { key: "port", label: "Porta TCP", type: "number" },
    { key: "unit_id", label: "ID unita", type: "number" },
  ],
};

const MODBUS_RTU_TCP_GUIDED_FIELDS: GuidedFieldConfig[] = [
  { key: "host", label: "Indirizzo host", type: "text" },
  { key: "port", label: "Porta TCP", type: "number" },
  { key: "unit_id", label: "ID unita", type: "number", aliases: ["slave_id", "address"] },
  { key: "timeout_seconds", label: "Timeout connessione (s)", type: "number" },
];

const PROTOCOL_PRIORITY: Record<string, number> = {
  modbus_tcp: 0,
  modbus_rtu: 1,
  sunspec: 2,
  aurora: 3,
  delta_rs485: 4,
};
type ConnectionScalar = string | number | boolean;

const PROTOCOL_REQUIRED_CONNECTION_FIELDS: Record<string, string[]> = {
  modbus_tcp: ["host", "port", "unit_id", "timeout_seconds", "retries"],
  modbus_rtu: [
    "port",
    "slave_id",
    "baud_rate",
    "parity",
    "stop_bits",
    "byte_size",
    "timeout_seconds",
    "retries",
  ],
  aurora: [
    "port",
    "address",
    "baud_rate",
    "parity",
    "stop_bits",
    "byte_size",
    "timeout_seconds",
    "retries",
  ],
  delta_rs485: [
    "port",
    "address",
    "baud_rate",
    "parity",
    "stop_bits",
    "byte_size",
    "timeout_seconds",
    "retries",
  ],
  sunspec: ["host", "port", "unit_id", "timeout_seconds", "retries"],
};

const PROTOCOL_REQUIRED_CONNECTION_FIELDS_BY_TRANSPORT: Record<string, string[]> = {
  "modbus_rtu:tcp": ["host", "port", "unit_id", "timeout_seconds", "retries"],
};

const PROTOCOL_CONNECTION_ALIASES: Record<string, Record<string, string>> = {
  modbus_tcp: { slave_id: "unit_id" },
  sunspec: { slave_id: "unit_id" },
  modbus_rtu: { unit_id: "slave_id", address: "slave_id" },
  aurora: { unit_id: "address", slave_id: "address" },
  delta_rs485: { unit_id: "address", slave_id: "address" },
};

const PROTOCOL_CONNECTION_ALIASES_BY_TRANSPORT: Record<string, Record<string, string>> = {
  "modbus_rtu:tcp": { slave_id: "unit_id", address: "unit_id" },
};

const BOOLEAN_CONNECTION_KEYS = new Set([
  "handle_local_echo",
  "use_rs485_mode",
  "rs485_rts_level_for_tx",
  "rs485_rts_level_for_rx",
  "rs485_loopback",
  "retry_on_device_busy",
]);

const INTEGER_CONNECTION_RANGES: Record<string, { min: number; max?: number }> = {
  port: { min: 1, max: 65535 },
  unit_id: { min: 0, max: 247 },
  slave_id: { min: 0, max: 247 },
  address: { min: 0, max: 247 },
  baud_rate: { min: 1 },
  stop_bits: { min: 1, max: 2 },
  byte_size: { min: 5, max: 8 },
  retries: { min: 0, max: 10 },
  device_busy_retry_count: { min: 0, max: 10 },
  max_registers_per_request: { min: 1, max: 125 },
  delta_variant: { min: 1, max: 4 },
};

const FLOAT_CONNECTION_RANGES: Record<string, { min: number; max?: number }> = {
  timeout_seconds: { min: 0.05, max: 60 },
  poll_interval_seconds: { min: 1, max: 300 },
  inter_request_delay_ms: { min: 0, max: 60000 },
  inter_request_delay_seconds: { min: 0, max: 60 },
  retry_delay_ms: { min: 0, max: 60000 },
  device_busy_retry_delay_ms: { min: 0, max: 60000 },
  rs485_delay_before_tx_ms: { min: 0, max: 60000 },
  rs485_delay_before_rx_ms: { min: 0, max: 60000 },
};

export function compareLabels(left: string, right: string): number {
  return left.localeCompare(right, "it", { numeric: true, sensitivity: "base" });
}

export function isTransportAllowedForProtocol(protocol: string, transport: string): boolean {
  const allowedTransports = PROTOCOL_ALLOWED_TRANSPORTS[protocol];
  if (!allowedTransports || !transport) {
    return false;
  }
  return allowedTransports.includes(transport);
}

export function getGuidedConnectionFields(
  protocol: string,
  transport: string,
): GuidedFieldConfig[] {
  if (protocol === "modbus_rtu" && transport === "tcp") {
    return MODBUS_RTU_TCP_GUIDED_FIELDS;
  }
  return GUIDED_CONNECTION_FIELDS[protocol] ?? [];
}

export function listCatalogBrands(catalogModels: CatalogModel[], currentBrand = ""): string[] {
  const brands = new Set(catalogModels.map((catalogModel) => catalogModel.brand));
  if (currentBrand) {
    brands.add(currentBrand);
  }

  return Array.from(brands).sort(compareLabels);
}

export function listCatalogModelsForBrand(
  catalogModels: CatalogModel[],
  brand: string,
  currentModel = "",
): CatalogModel[] {
  const uniqueModels = new Map<string, CatalogModel>();

  for (const catalogModel of catalogModels) {
    if (catalogModel.brand !== brand || uniqueModels.has(catalogModel.model)) {
      continue;
    }
    uniqueModels.set(catalogModel.model, catalogModel);
  }

  if (currentModel && !uniqueModels.has(currentModel)) {
    uniqueModels.set(currentModel, {
      brand,
      model: currentModel,
      protocol: "",
      transport: "",
      defaults: {},
      features: [],
      telemetry_count: 0,
      visible_telemetry_count: 0,
      command_count: 0,
      writable_command_count: 0,
      alarm_count: 0,
      discovery_signature: {
        register: null,
        function: null,
      },
      capabilities: {
        has_active_power_limit: false,
        has_reactive_power_control: false,
        has_start_stop_control: false,
        supports_live_telemetry: false,
        supports_power_history: false,
      },
    });
  }

  return Array.from(uniqueModels.values()).sort((left, right) =>
    compareLabels(left.model, right.model),
  );
}

export function findCatalogEntry(
  catalogModels: CatalogModel[],
  brand: string,
  model: string,
  preferredProtocol?: string,
): CatalogModel | null {
  const matches = catalogModels.filter(
    (catalogModel) => catalogModel.brand === brand && catalogModel.model === model,
  );
  if (matches.length === 0) {
    return null;
  }

  if (preferredProtocol) {
    const exactMatch = matches.find((catalogModel) => catalogModel.protocol === preferredProtocol);
    if (exactMatch) {
      return exactMatch;
    }
  }

  return (
    [...matches].sort((left, right) => {
      const leftPriority = PROTOCOL_PRIORITY[left.protocol] ?? 99;
      const rightPriority = PROTOCOL_PRIORITY[right.protocol] ?? 99;
      if (leftPriority !== rightPriority) {
        return leftPriority - rightPriority;
      }
      return compareLabels(left.protocol, right.protocol);
    })[0] ?? null
  );
}

export function parseConnectionSettings(text: string): ConnectionSettings {
  const parsed = JSON.parse(text) as unknown;

  if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("Le impostazioni di connessione devono essere un oggetto JSON valido.");
  }

  return parsed as ConnectionSettings;
}

export function parseConnectionSettingsSafe(text: string): ConnectionSettings | null {
  try {
    return parseConnectionSettings(text);
  } catch {
    return null;
  }
}

function translateConnectionValidationKey(key: string): string {
  switch (key) {
    case "host":
      return "host";
    case "port":
      return "porta";
    case "unit_id":
      return "ID unita";
    case "slave_id":
      return "ID slave";
    case "address":
      return "indirizzo";
    case "baud_rate":
      return "baud rate";
    case "parity":
      return "parita";
    case "stop_bits":
      return "bit di stop";
    case "byte_size":
      return "dimensione byte";
    case "timeout_seconds":
      return "timeout";
    case "retries":
      return "tentativi";
    case "poll_interval_seconds":
      return "intervallo polling";
    case "delta_variant":
      return "variante Delta";
    case "device_busy_retry_count":
      return "tentativi device busy";
    case "device_busy_retry_delay_ms":
      return "attesa device busy";
    case "inter_request_delay_ms":
      return "attesa tra richieste";
    case "inter_request_delay_seconds":
      return "attesa tra richieste";
    case "max_registers_per_request":
      return "registri per richiesta";
    default:
      return key.split("_").join(" ");
  }
}

function isMissingConnectionValue(value: ConnectionScalar | undefined): boolean {
  return value === undefined || (typeof value === "string" && value.trim() === "");
}

function parseConnectionInteger(key: string, value: ConnectionScalar): number {
  if (typeof value === "boolean" || value === "") {
    throw new Error(`Il parametro '${translateConnectionValidationKey(key)}' deve essere numerico.`);
  }
  const numericValue = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(numericValue)) {
    throw new Error(`Il parametro '${translateConnectionValidationKey(key)}' deve essere un intero.`);
  }
  return numericValue;
}

function parseConnectionFloat(key: string, value: ConnectionScalar): number {
  if (typeof value === "boolean" || value === "") {
    throw new Error(`Il parametro '${translateConnectionValidationKey(key)}' deve essere numerico.`);
  }
  const numericValue = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numericValue)) {
    throw new Error(`Il parametro '${translateConnectionValidationKey(key)}' deve essere numerico.`);
  }
  return numericValue;
}

function parseConnectionBoolean(key: string, value: ConnectionScalar): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(normalized)) {
      return true;
    }
    if (["0", "false", "no", "off"].includes(normalized)) {
      return false;
    }
  }
  throw new Error(`Il parametro '${translateConnectionValidationKey(key)}' deve essere true o false.`);
}

export function normalizeConnectionSettings(
  protocol: string,
  transport: string,
  settings: ConnectionSettings,
  options?: { requireRequiredSettings?: boolean },
): ConnectionSettings {
  if (!protocol) {
    throw new Error("Seleziona un protocollo prima di definire i parametri di connessione.");
  }
  if (!transport) {
    throw new Error("Seleziona un trasporto prima di definire i parametri di connessione.");
  }
  if (!isTransportAllowedForProtocol(protocol, transport)) {
    throw new Error("Il trasporto selezionato non corrisponde al protocollo scelto.");
  }

  const normalized: ConnectionSettings = {
    ...(PROTOCOL_TRANSPORT_DEFAULT_SETTINGS[`${protocol}:${transport}`] ??
      PROTOCOL_DEFAULT_SETTINGS[protocol] ??
      {}),
  };

  for (const [key, rawValue] of Object.entries(settings)) {
    if (typeof rawValue === "string") {
      normalized[key] = BOOLEAN_CONNECTION_KEYS.has(key) ? parseConnectionBoolean(key, rawValue) : rawValue.trim();
      continue;
    }
    normalized[key] = rawValue;
  }

  const aliases = {
    ...(PROTOCOL_CONNECTION_ALIASES[protocol] ?? {}),
    ...(PROTOCOL_CONNECTION_ALIASES_BY_TRANSPORT[`${protocol}:${transport}`] ?? {}),
  };
  for (const [alias, canonical] of Object.entries(aliases)) {
    if (normalized[canonical] !== undefined || normalized[alias] === undefined) {
      continue;
    }
    normalized[canonical] = normalized[alias];
    delete normalized[alias];
  }

  if (transport === "tcp") {
    const host = normalized.host;
    if (!isMissingConnectionValue(host)) {
      if (typeof host !== "string" || host.trim() === "") {
        throw new Error("Il parametro 'host' deve contenere un indirizzo valido.");
      }
      normalized.host = host.trim();
    }
  } else {
    const port = normalized.port;
    if (!isMissingConnectionValue(port)) {
      if (typeof port !== "string" || port.trim() === "") {
        throw new Error("Il parametro 'porta' deve contenere una porta seriale valida.");
      }
      normalized.port = port.trim();
    }
  }

  for (const [key, range] of Object.entries(INTEGER_CONNECTION_RANGES)) {
    if (key === "port" && transport !== "tcp") {
      continue;
    }
    const rawValue = normalized[key];
    if (isMissingConnectionValue(rawValue)) {
      continue;
    }
    const parsed = parseConnectionInteger(key, rawValue);
    if (parsed < range.min || (range.max !== undefined && parsed > range.max)) {
      if (key === "delta_variant") {
        throw new Error("Il parametro 'variante Delta' deve essere 1, 3 o 4.");
      }
      throw new Error(
        range.max !== undefined
          ? `Il parametro '${translateConnectionValidationKey(key)}' deve restare tra ${range.min} e ${range.max}.`
          : `Il parametro '${translateConnectionValidationKey(key)}' deve essere almeno ${range.min}.`,
      );
    }
    normalized[key] = parsed;
  }

  for (const [key, range] of Object.entries(FLOAT_CONNECTION_RANGES)) {
    const rawValue = normalized[key];
    if (isMissingConnectionValue(rawValue)) {
      continue;
    }
    const parsed = parseConnectionFloat(key, rawValue);
    if (parsed < range.min || (range.max !== undefined && parsed > range.max)) {
      throw new Error(
        range.max !== undefined
          ? `Il parametro '${translateConnectionValidationKey(key)}' deve restare tra ${range.min} e ${range.max}.`
          : `Il parametro '${translateConnectionValidationKey(key)}' deve essere almeno ${range.min}.`,
      );
    }
    normalized[key] = Number.isInteger(parsed) ? Math.trunc(parsed) : parsed;
  }

  const parityValue = normalized.parity;
  if (!isMissingConnectionValue(parityValue)) {
    if (typeof parityValue !== "string") {
      throw new Error("Il parametro 'parita' deve essere una stringa.");
    }
    const parity = parityValue.trim().toUpperCase();
    if (!["N", "E", "O", "M", "S"].includes(parity)) {
      throw new Error("Il parametro 'parita' deve essere uno tra N, E, O, M, S.");
    }
    normalized.parity = parity;
  }

  if (protocol !== "delta_rs485") {
    delete normalized.delta_variant;
  }

  if (options?.requireRequiredSettings !== false) {
    const missing = (
      PROTOCOL_REQUIRED_CONNECTION_FIELDS_BY_TRANSPORT[`${protocol}:${transport}`] ??
      PROTOCOL_REQUIRED_CONNECTION_FIELDS[protocol] ??
      []
    ).filter((key) =>
      isMissingConnectionValue(normalized[key]),
    );
    if (missing.length > 0) {
      throw new Error(
        `Parametri di connessione mancanti: ${missing
          .map((key) => translateConnectionValidationKey(key))
          .join(", ")}.`,
      );
    }
  }

  return normalized;
}

export function buildConnectionSettingsError(
  protocol: string,
  transport: string,
  connectionSettingsText: string,
): string | null {
  try {
    const settings = parseConnectionSettings(connectionSettingsText);
    normalizeConnectionSettings(protocol, transport, settings);
    return null;
  } catch (error) {
    return error instanceof Error
      ? error.message
      : "Le impostazioni di connessione non sono valide.";
  }
}

export function formatConnectionSettingsText(settings: ConnectionSettings): string {
  return JSON.stringify(settings, null, 2);
}

export function buildProtocolSettings(
  protocol: string,
  settings: ConnectionSettings | null,
  transport?: string,
): ConnectionSettings {
  return {
    ...(transport
      ? (PROTOCOL_TRANSPORT_DEFAULT_SETTINGS[`${protocol}:${transport}`] ??
        PROTOCOL_DEFAULT_SETTINGS[protocol] ??
        {})
      : (PROTOCOL_DEFAULT_SETTINGS[protocol] ?? {})),
    ...(settings ?? {}),
  };
}

export function getGuidedFieldValue(
  settings: ConnectionSettings | null,
  field: GuidedFieldConfig,
): string {
  const keys = [field.key, ...(field.aliases ?? [])];

  for (const key of keys) {
    const value = settings?.[key];
    if (value !== undefined && value !== null) {
      return String(value);
    }
  }

  return "";
}

function normalizeSerialPortName(portName: string): string {
  const trimmedValue = portName.trim();
  if (trimmedValue.length <= 1) {
    return trimmedValue;
  }
  return trimmedValue.replace(/[\\/]+$/, "");
}

export function getSerialPortDisplayName(portName: string): string {
  const normalizedPortName = normalizeSerialPortName(portName);
  return SERIAL_PORT_DISPLAY_NAMES[normalizedPortName] ?? portName;
}

export function buildSerialPortLabel(serialPort: SerialPortInfo): string {
  const displayName = getSerialPortDisplayName(serialPort.name);
  if (displayName !== serialPort.name) {
    return displayName;
  }
  return serialPort.description
    ? `${serialPort.name} | ${serialPort.description}`
    : serialPort.name;
}

export function buildSerialPortOptions(
  serialPorts: SerialPortInfo[],
  currentValue: string,
): GuidedFieldOption[] {
  const options = serialPorts.map((serialPort) => ({
    value: serialPort.name,
    label: buildSerialPortLabel(serialPort),
  }));

  if (currentValue && !serialPorts.some((serialPort) => serialPort.name === currentValue)) {
    return [
      {
        value: currentValue,
        label: `${getSerialPortDisplayName(currentValue)} | valore corrente`,
      },
      ...options,
    ];
  }

  return options;
}

export function buildCreatePayload(form: ProvisionFormState): CreateDevicePayload {
  const name = form.name.trim();
  const brand = form.brand.trim();
  const model = form.model.trim();

  if (!name || !brand || !model || !form.protocol || !form.transport || !form.status) {
    throw new Error("Compila tutti i campi obbligatori prima di salvare il dispositivo.");
  }

  return {
    name,
    brand,
    model,
    protocol: form.protocol,
    transport: form.transport,
    connection_settings: normalizeConnectionSettings(
      form.protocol,
      form.transport,
      parseConnectionSettings(form.connectionSettingsText),
    ),
  };
}

export function buildUpdatePayload(form: ProvisionFormState): UpdateDevicePayload {
  return {
    ...buildCreatePayload(form),
    status: form.status,
  };
}

export function buildConnectionTestPayload(form: ProvisionFormState): ProtocolTestPayload {
  if (!form.protocol || !form.transport) {
    throw new Error("Seleziona protocollo e trasporto prima di testare la connessione.");
  }

  return {
    protocol: form.protocol,
    transport: form.transport,
    brand: form.brand.trim() || undefined,
    model: form.model.trim() || undefined,
    connection_settings: normalizeConnectionSettings(
      form.protocol,
      form.transport,
      parseConnectionSettings(form.connectionSettingsText),
    ),
    profile_overrides: {},
  };
}

export function translateStatusLabel(status: string): string {
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

export function translateTestMessage(message: string): string {
  switch (message) {
    case "Stub connection test passed.":
      return "Test di connessione stub riuscito.";
    case "Stub connection test failed.":
      return "Test di connessione stub non riuscito.";
    case "Unsupported protocol for stub connection test.":
      return "Protocollo non supportato per il test di connessione stub.";
    case "Unsupported protocol for connection test.":
      return "Protocollo non supportato per il test di connessione.";
    case "Transport does not match the selected protocol.":
      return "Il trasporto selezionato non corrisponde al protocollo scelto.";
    case "Missing connection settings for the selected protocol.":
      return "Mancano alcuni parametri di connessione richiesti per il protocollo selezionato.";
    case "Selected model is not available in the inverter catalog.":
      return "Il modello selezionato non e disponibile nel catalogo inverter.";
    case "Profile-aware connection test passed.":
      return "Test di connessione sul profilo del modello riuscito.";
    case "Connection test failed for the selected inverter profile.":
      return "Test di connessione sul profilo del modello non riuscito.";
    case "Generic connection test passed.":
      return "Test di connessione generico riuscito.";
    case "Generic connection test failed.":
      return "Test di connessione generico non riuscito.";
    case "Delta RS485 connection test passed.":
      return "Test di connessione Delta RS485 riuscito.";
    case "Delta RS485 connection test failed.":
      return "Test di connessione Delta RS485 non riuscito.";
    case "Aurora connection test passed.":
      return "Test di connessione Aurora riuscito.";
    case "Aurora connection test failed.":
      return "Test di connessione Aurora non riuscito.";
    default:
      return message;
  }
}

export function translateDiagnosticLabel(key: string): string {
  switch (key) {
    case "stub_mode":
      return "Modalita stub";
    case "stage":
      return "Fase";
    case "expected_transport":
      return "Trasporto atteso";
    case "provided_settings_count":
      return "Numero parametri forniti";
    case "required_settings_count":
      return "Numero parametri richiesti";
    case "missing_settings":
      return "Parametri mancanti";
    case "elapsed_ms":
      return "Durata test";
    case "telemetry_values_read":
      return "Valori telemetria letti";
    case "unit_argument_style":
      return "Parametro unit";
    case "probe_register":
      return "Registro di probe";
    case "probe_function":
      return "Funzione di probe";
    case "raw_values":
      return "Valori letti";
    case "resolved_variant":
      return "Variante risolta";
    case "family_model":
      return "Famiglia modello";
    case "identified_model_name":
      return "Modello identificato";
    case "serial_number":
      return "Numero seriale";
    case "part_number":
      return "Part number";
    case "part_number_raw":
      return "Part number grezzo";
    case "part_number_source":
      return "Sorgente part number";
    case "payload_bytes":
      return "Byte payload";
    case "driver":
      return "Driver";
    case "global_state":
      return "Stato globale";
    case "inverter_state":
      return "Stato inverter";
    case "dcdc1_state":
      return "Stato DC/DC 1";
    case "dcdc2_state":
      return "Stato DC/DC 2";
    case "alarm_code":
      return "Codice allarme";
    case "model_code":
      return "Codice modello";
    case "grid_code":
      return "Codice rete";
    case "transformer_code":
      return "Codice trasformatore";
    case "application_code":
      return "Codice applicazione";
    case "version_signature":
      return "Firma versione";
    case "resolved_candidate_count":
      return "Profili risolti";
    case "resolved_brand":
      return "Marca risolta";
    case "resolved_model":
      return "Modello risolto";
    case "aurora_address":
      return "Indirizzo Aurora";
    case "aurora_op":
      return "Opcode Aurora";
    case "aurora_operation":
      return "Operazione Aurora";
    case "aurora_attempt":
      return "Tentativo Aurora";
    case "aurora_retry_budget":
      return "Retry Aurora";
    case "aurora_tx_frame":
      return "Frame TX Aurora";
    case "aurora_rx_buffer":
      return "Buffer RX Aurora";
    case "aurora_reply_frame":
      return "Reply Aurora";
    case "aurora_reply_tx_state":
      return "TxState Aurora";
    case "aurora_reply_tx_state_label":
      return "Dettaglio TxState Aurora";
    case "aurora_crc_expected":
      return "CRC atteso Aurora";
    case "aurora_crc_received":
      return "CRC ricevuto Aurora";
    case "aurora_received_bytes":
      return "Byte ricevuti Aurora";
    default:
      return key.split("_").join(" ");
  }
}

function translateTransportValue(value: string): string {
  switch (value) {
    case "tcp":
      return "TCP";
    case "serial":
      return "Seriale";
    default:
      return value;
  }
}

function translateAuroraTxState(value: number): string | null {
  switch (value) {
    case 0:
      return "OK";
    case 51:
      return "Comando non implementato";
    case 52:
      return "Variabile non disponibile";
    case 53:
      return "Valore fuori range";
    case 54:
      return "EEPROM non accessibile";
    case 55:
      return "Service mode non attivata";
    case 56:
      return "Comando non inoltrabile al micro interno";
    case 57:
      return "Comando non eseguito";
    case 58:
      return "Variabile non disponibile, riprovare";
    default:
      return null;
  }
}

function translateDiagnosticStage(value: string): string {
  switch (value) {
    case "protocol":
      return "Validazione protocollo";
    case "transport":
      return "Validazione trasporto";
    case "settings":
      return "Validazione parametri";
    case "connect":
      return "Connessione";
    case "profile":
      return "Profilo modello";
    case "generic":
      return "Probe generica";
    case "delta_probe":
      return "Probe Delta RS485";
    case "aurora_probe":
      return "Probe Aurora";
    default:
      return value.split("_").join(" ");
  }
}

function translateUnitArgumentStyle(value: string): string {
  switch (value) {
    case "device_id":
      return "Parametro device_id";
    case "slave":
      return "Parametro slave";
    case "none":
      return "Nessun parametro unit";
    case "not_attempted":
      return "Non eseguito";
    default:
      return value;
  }
}

function translateConnectionSettingKey(value: string): string {
  switch (value) {
    case "host":
      return "host";
    case "port":
      return "porta";
    case "unit_id":
      return "ID unita";
    case "slave_id":
      return "ID slave";
    case "address":
      return "indirizzo";
    case "baud_rate":
      return "baud rate";
    case "parity":
      return "parita";
    case "stop_bits":
      return "bit di stop";
    case "byte_size":
      return "dimensione byte";
    case "timeout_seconds":
      return "timeout";
    case "retries":
      return "tentativi";
    default:
      return value.split("_").join(" ");
  }
}

export function formatDiagnosticValue(
  key: string,
  value: string | number | boolean,
): string {
  if (value === true) {
    return "Si";
  }

  if (value === false) {
    return "No";
  }

  if (value === "none") {
    return "nessuno";
  }

  if (key === "stage" && typeof value === "string") {
    return translateDiagnosticStage(value);
  }

  if (key === "expected_transport" && typeof value === "string") {
    return translateTransportValue(value);
  }

  if (key === "unit_argument_style" && typeof value === "string") {
    return translateUnitArgumentStyle(value);
  }

  if (key === "missing_settings" && typeof value === "string") {
    return value
      .split(",")
      .map((item) => translateConnectionSettingKey(item.trim()))
      .join(", ");
  }

  if (key === "probe_function" && typeof value === "string") {
    return value === "holding" ? "Holding register" : value === "input" ? "Input register" : value;
  }

  if (key === "part_number_source" && typeof value === "string") {
    if (value === "op_52") {
      return "P/N reading (52)";
    }
    if (value === "op_105") {
      return "System P/N reading (105)";
    }
  }

  if (key === "aurora_reply_tx_state" && typeof value === "number") {
    const label = translateAuroraTxState(value);
    return label ? `${value} - ${label}` : String(value);
  }

  if (key === "elapsed_ms" && typeof value === "number") {
    return `${value} ms`;
  }

  return String(value);
}

export function buildFormStateFromDevice(device: Device): ProvisionFormState {
  return {
    name: device.name,
    brand: device.brand,
    model: device.model,
    protocol: device.protocol,
    transport: device.transport,
    status: device.status,
    connectionSettingsText: formatConnectionSettingsText(device.connection_settings),
  };
}

export function buildTestResultTitle(result: ProtocolTestResult): string {
  return result.success ? "Connessione riuscita" : "Connessione non riuscita";
}
