import { type CSSProperties, type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import {
  clearFleetControlSetpoint,
  confirmNetworkConfiguration,
  deleteAllDevices,
  deleteDevice,
  getFleetControlStatus,
  getDashboardPowerHistory,
  getDashboardSummary,
  getDeviceOverview,
  getDevices,
  getNetworkConfiguration,
  getSerialPorts,
  getSystemHealth,
  rollbackNetworkConfiguration,
  sendActivePowerLimit,
  setFleetControlSetpoint,
  updateHsmBridgeConfig,
  updateModbusTcpSlaveConfig,
  type DashboardSummary,
  type Device,
  type DeviceOverview,
  type DeviceOverviewTelemetryPoint,
  type FleetControlConfidence,
  type FleetReadiness,
  type FleetReadinessCheck,
  type FleetControlStatus,
  type FleetTimelineEvent,
  type FleetPowerHistoryResponse,
  type PendingNetworkChange,
  type PowerHistoryQuery,
  type SerialPortInfo,
  type SystemHealthBroadcastGroup,
  type SystemHealthResponse,
} from "./api";
import { AddDeviceModal } from "./components/AddDeviceModal";
import { AdvancedHistoryDrawer } from "./components/AdvancedHistoryDrawer";
import { DeviceConnectionDrawer } from "./components/DeviceConnectionDrawer";
import {
  DeviceDiscoveryModal,
  type DeviceDiscoveryPrefill,
} from "./components/DeviceDiscoveryModal";
import { DrawerErrorBoundary } from "./components/DrawerErrorBoundary";
import { DeviceDetailPanel } from "./components/DeviceDetailPanel";
import { InverterFlowScene } from "./components/InverterFlowScene";
import {
  OperatorProvisioningDrawer,
  type OperatorProvisioningProgressState,
} from "./components/OperatorProvisioningDrawer";
import { SystemHealthDrawer } from "./components/SystemHealthDrawer";
import { SystemSettingsDrawer } from "./components/SystemSettingsDrawer";
import {
  DEFAULT_POWER_HISTORY_RANGE_PRESET,
  POWER_HISTORY_RANGE_PRESETS,
  PowerHistoryChart,
  type PowerHistoryRangePresetId,
  type PowerHistoryChartSeries,
} from "./components/PowerHistoryChart";
import {
  buildSerialPortLabel,
  getSerialPortDisplayName,
} from "./components/deviceProvisioningShared";
import {
  buildOrderedTelemetrySections,
  buildTelemetrySectionNote,
  translateTelemetryLabel,
  translateTelemetrySection,
} from "./telemetryPresentation";
import {
  getSettingsAccentClass,
  SETTINGS_SECTION_CONTENT,
  type SettingsGuidanceItem,
  type SettingsSectionAccent,
} from "./settingsSections";
import {
  AC_SIGNAL_DEFINITIONS,
  DC_SIGNAL_DEFINITIONS,
  pickTelemetrySignals,
} from "./sceneTelemetry";

type SummaryTone = "neutral" | "positive" | "warning";

type SummaryItem = {
  label: string;
  value: string;
  caption: string;
  tone: SummaryTone;
};

type DataGroup = {
  title: string;
  value: string;
  note: string;
  rows: Array<{ label: string; value: string }>;
};

type DevicePowerMap = Record<string, number | null>;
type DeviceOverviewMap = Record<string, DeviceOverview | null>;

type FirstConnectWatchTarget = {
  deviceId: string;
  name: string;
};

type FirstConnectWatchState = {
  startedAt: number;
  targets: FirstConnectWatchTarget[];
};

type LiveFocusItem = {
  label: string;
  value: string;
  note: string;
  tone: SummaryTone;
};

type MobileStageTab = "live" | "history" | "focus" | "commands";
type DashboardMode = "lite" | "operator" | "pro";
type OperatorDeviceStatusFilter =
  | "all"
  | "online"
  | "pending"
  | "degraded"
  | "offline"
  | "warning"
  | "fault";
type OperatorDeviceSortMode = "status" | "name" | "power_desc" | "power_asc";
type PowerHistoryRangeMode = "preset" | "custom";

type PowerHistoryRangeSelection = {
  presetId: PowerHistoryRangePresetId;
  mode: PowerHistoryRangeMode;
  startIso: string;
  endIso: string;
  isLive: boolean;
};

type StageTabOption = {
  key: MobileStageTab;
  label: string;
};

type OperationalGuidance = {
  value: string;
  note: string;
  tone: SummaryTone;
};

type OperatorCommandabilityState = "ready" | "warning" | "blocked" | "idle";

type OperatorCommandabilityMetric = {
  label: string;
  value: string;
  note: string;
  tone: SummaryTone;
};

type OperatorCommandabilitySnapshot = {
  state: OperatorCommandabilityState;
  answer: string;
  headline: string;
  detail: string;
  metrics: OperatorCommandabilityMetric[];
  issues: string[];
};

type AppDialogTone = "info" | "success" | "warning" | "error";

type DeleteDialogState =
  | {
      kind: "single";
      device: Device;
    }
  | {
      kind: "bulk";
      count: number;
      stage: "initial" | "final";
    };

type NoticeDialogState = {
  title: string;
  message: string;
  tone: AppDialogTone;
  confirmLabel?: string;
};

type ModbusSlaveSettingsDraft = {
  enabled: boolean;
  host: string;
  port: string;
  unitId: string;
  cciReadbackEnabled: boolean;
  cciReadbackRangePercent: string;
  cciReadbackStableSeconds: string;
  cciReadbackActivePowerOnly: boolean;
};

type HsmBridgeSettingsDraft = {
  enabled: boolean;
  hsmPort: string;
  inverterPort: string;
  hsmBaudRate: string;
  hsmParity: "N" | "E" | "O";
  hsmStopBits: string;
  hsmByteSize: string;
  frameGapMs: string;
  forwardDelayMs: string;
  ackTimeoutMs: string;
};

type OperatorComSettingsSectionKey = "slave" | "bridge";

type SolarAmbientPalette = {
  minute: number;
  skyTop: string;
  skyMid: string;
  skyBottom: string;
  horizonGlow: string;
};

type SolarAmbientFrame = {
  skyTop: string;
  skyMid: string;
  skyBottom: string;
  horizonGlow: string;
  sunX: number;
  sunY: number;
  sunOpacity: number;
  sunScale: number;
  sunTint: string;
};

type SolarTimeSyncState = {
  offsetMs: number;
  source: "internet" | "pc";
};

type RomeDateTimeParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
};

type SolarDayTimes = {
  sunriseMinute: number;
  sunsetMinute: number;
};

type ReferenceDeviceContext = {
  device: Device;
  overview: DeviceOverview;
};

const integerFormatter = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 });
const metricFormatter = new Intl.NumberFormat("it-IT", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const DASHBOARD_MODE_STORAGE_KEY = "pv-edge-manager.dashboard-mode";
const SOLAR_BACKGROUND_STORAGE_KEY = "pv-edge-manager.solar-background-enabled";
const SOLAR_BACKGROUND_UPDATE_MS = 60_000;
const SOLAR_TIME_RESYNC_MS = 30 * 60_000;
const SOLAR_TIME_FETCH_TIMEOUT_MS = 2500;
const SOLAR_TIME_ZONE = "Europe/Rome";
const ITALY_AVERAGE_LATITUDE = 42.8;
const ITALY_AVERAGE_LONGITUDE = 12.5;
const DASHBOARD_LIVE_REFRESH_MS = 2500;
const DASHBOARD_OVERVIEW_FALLBACK_REFRESH_MS = 5000;
const FLEET_CONTROL_FAST_REFRESH_MS = 1500;
const SELECTED_DEVICE_REFRESH_MS = 2500;
const POWER_HISTORY_REFRESH_MS = 10000;
const OPERATOR_STATUS_FILTER_OPTIONS: Array<{
  value: OperatorDeviceStatusFilter;
  label: string;
}> = [
  { value: "all", label: "Tutti" },
  { value: "online", label: "Online" },
  { value: "pending", label: "In attesa" },
  { value: "degraded", label: "Parziali" },
  { value: "offline", label: "Offline" },
  { value: "warning", label: "Avvisi" },
  { value: "fault", label: "Guasti" },
];
const OPERATOR_SORT_OPTIONS: Array<{ value: OperatorDeviceSortMode; label: string }> = [
  { value: "status", label: "Stato" },
  { value: "name", label: "Nome" },
  { value: "power_desc", label: "Potenza ↓" },
  { value: "power_asc", label: "Potenza ↑" },
];
const dateTimeFormatter = new Intl.DateTimeFormat("it-IT", {
  dateStyle: "medium",
  timeStyle: "short",
});
const OPERATOR_PLANT_CHART_EMPTY_STATE: Record<string, string> = {
  emptyMessage:
    "La dashboard operatore mostrera totale e singoli inverter non appena il backend avra campioni reali di potenza.",
};

const SOLAR_TIME_ENDPOINTS = [
  "https://worldtimeapi.org/api/timezone/Europe/Rome",
  "https://timeapi.io/api/time/current/zone?timeZone=Europe/Rome",
];

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function smoothStep(value: number): number {
  const clampedValue = clampNumber(value, 0, 1);
  return clampedValue * clampedValue * (3 - 2 * clampedValue);
}

function mixNumber(start: number, end: number, ratio: number): number {
  return Math.round(start + (end - start) * ratio);
}

function hexToRgb(hexColor: string): [number, number, number] {
  const normalized = hexColor.replace("#", "");
  const parsed = Number.parseInt(normalized, 16);
  return [(parsed >> 16) & 255, (parsed >> 8) & 255, parsed & 255];
}

function mixHexColor(start: string, end: string, ratio: number): string {
  const startRgb = hexToRgb(start);
  const endRgb = hexToRgb(end);
  return `rgb(${mixNumber(startRgb[0], endRgb[0], ratio)}, ${mixNumber(
    startRgb[1],
    endRgb[1],
    ratio,
  )}, ${mixNumber(startRgb[2], endRgb[2], ratio)})`;
}

const romeDateTimeFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: SOLAR_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

function getRomeDateTimeParts(date: Date): RomeDateTimeParts {
  const parts = romeDateTimeFormatter.formatToParts(date).reduce<Record<string, string>>(
    (current, part) => {
      if (part.type !== "literal") {
        current[part.type] = part.value;
      }
      return current;
    },
    {},
  );

  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: Number(parts.hour),
    minute: Number(parts.minute),
    second: Number(parts.second),
  };
}

function getDayOfYear({ year, month, day }: RomeDateTimeParts): number {
  const startOfYear = Date.UTC(year, 0, 0);
  const targetDate = Date.UTC(year, month - 1, day);
  return Math.floor((targetDate - startOfYear) / 86_400_000);
}

function getTimeZoneOffsetMinutes(date: Date): number {
  const parts = getRomeDateTimeParts(date);
  const localAsUtc = Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
    parts.second,
  );
  return Math.round((localAsUtc - date.getTime()) / 60_000);
}

function calculateAverageItalianSolarTimes(date: Date): SolarDayTimes {
  const romeParts = getRomeDateTimeParts(date);
  const dayOfYear = getDayOfYear(romeParts);
  const gamma = (2 * Math.PI * (dayOfYear - 1)) / 365;
  const equationOfTime =
    229.18 *
    (0.000075 +
      0.001868 * Math.cos(gamma) -
      0.032077 * Math.sin(gamma) -
      0.014615 * Math.cos(2 * gamma) -
      0.040849 * Math.sin(2 * gamma));
  const solarDeclination =
    0.006918 -
    0.399912 * Math.cos(gamma) +
    0.070257 * Math.sin(gamma) -
    0.006758 * Math.cos(2 * gamma) +
    0.000907 * Math.sin(2 * gamma) -
    0.002697 * Math.cos(3 * gamma) +
    0.00148 * Math.sin(3 * gamma);
  const latitudeRadians = (ITALY_AVERAGE_LATITUDE * Math.PI) / 180;
  const solarZenithRadians = (90.833 * Math.PI) / 180;
  const hourAngleInput =
    Math.cos(solarZenithRadians) / (Math.cos(latitudeRadians) * Math.cos(solarDeclination)) -
    Math.tan(latitudeRadians) * Math.tan(solarDeclination);
  const hourAngleDegrees =
    (Math.acos(clampNumber(hourAngleInput, -1, 1)) * 180) / Math.PI;
  const timeZoneOffsetMinutes = getTimeZoneOffsetMinutes(date);
  const sunriseUtc =
    720 - 4 * (ITALY_AVERAGE_LONGITUDE + hourAngleDegrees) - equationOfTime;
  const sunsetUtc =
    720 - 4 * (ITALY_AVERAGE_LONGITUDE - hourAngleDegrees) - equationOfTime;

  return {
    sunriseMinute: clampNumber(Math.round(sunriseUtc + timeZoneOffsetMinutes), 0, 1440),
    sunsetMinute: clampNumber(Math.round(sunsetUtc + timeZoneOffsetMinutes), 0, 1440),
  };
}

function normalizeSolarAmbientPalette(palette: SolarAmbientPalette[]): SolarAmbientPalette[] {
  return palette
    .map((item) => ({
      ...item,
      minute: Math.round(clampNumber(item.minute, 0, 1440)),
    }))
    .sort((first, second) => first.minute - second.minute)
    .reduce<SolarAmbientPalette[]>((items, item) => {
      const previous = items[items.length - 1];
      if (previous && previous.minute === item.minute) {
        items[items.length - 1] = item;
        return items;
      }
      items.push(item);
      return items;
    }, []);
}

function buildSolarAmbientPalette({
  sunriseMinute,
  sunsetMinute,
}: SolarDayTimes): SolarAmbientPalette[] {
  const solarNoonMinute = (sunriseMinute + sunsetMinute) / 2;
  return normalizeSolarAmbientPalette([
    {
      minute: 0,
      skyTop: "#06111d",
      skyMid: "#071525",
      skyBottom: "#08101b",
      horizonGlow: "rgba(82, 116, 176, 0.1)",
    },
    {
      minute: sunriseMinute - 55,
      skyTop: "#0a1a2b",
      skyMid: "#12304a",
      skyBottom: "#3f4565",
      horizonGlow: "rgba(255, 173, 105, 0.14)",
    },
    {
      minute: sunriseMinute,
      skyTop: "#12304a",
      skyMid: "#1e5f83",
      skyBottom: "#f0a86d",
      horizonGlow: "rgba(255, 173, 105, 0.26)",
    },
    {
      minute: sunriseMinute + 150,
      skyTop: "#3c83b5",
      skyMid: "#6ab5d6",
      skyBottom: "#d7f0ff",
      horizonGlow: "rgba(255, 236, 176, 0.2)",
    },
    {
      minute: solarNoonMinute,
      skyTop: "#4d93c6",
      skyMid: "#82c4e1",
      skyBottom: "#eff9ff",
      horizonGlow: "rgba(255, 245, 198, 0.22)",
    },
    {
      minute: sunsetMinute - 210,
      skyTop: "#2f6f9f",
      skyMid: "#6aa6c7",
      skyBottom: "#f2c281",
      horizonGlow: "rgba(255, 190, 112, 0.24)",
    },
    {
      minute: sunsetMinute,
      skyTop: "#101f35",
      skyMid: "#304878",
      skyBottom: "#e97862",
      horizonGlow: "rgba(255, 122, 97, 0.24)",
    },
    {
      minute: sunsetMinute + 60,
      skyTop: "#071421",
      skyMid: "#101f35",
      skyBottom: "#121522",
      horizonGlow: "rgba(255, 122, 97, 0.1)",
    },
    {
      minute: 1440,
      skyTop: "#06111d",
      skyMid: "#071525",
      skyBottom: "#08101b",
      horizonGlow: "rgba(82, 116, 176, 0.1)",
    },
  ]);
}

async function fetchJsonWithTimeout(url: string, timeoutMs: number): Promise<unknown> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => {
    controller.abort();
  }, timeoutMs);

  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`Time endpoint ${response.status}`);
    }
    return await response.json();
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function parseInternetTimePayload(payload: unknown): Date | null {
  if (payload === null || typeof payload !== "object") {
    return null;
  }
  const data = payload as Record<string, unknown>;
  const payloadTimeZone = typeof data.timeZone === "string" ? data.timeZone : null;
  const candidates = [
    data.datetime,
    data.utc_datetime,
    data.dateTime,
    data.currentDateTime,
    data.currentLocalTime,
  ];

  for (const candidate of candidates) {
    if (typeof candidate !== "string" || candidate.trim() === "") {
      continue;
    }
    if (
      payloadTimeZone === SOLAR_TIME_ZONE &&
      !/[zZ]|[+-]\d{2}:?\d{2}$/.test(candidate.trim())
    ) {
      const romeLocalDate = parseRomeLocalDateTime(candidate);
      if (romeLocalDate !== null) {
        return romeLocalDate;
      }
    }
    const parsedDate = new Date(candidate);
    if (!Number.isNaN(parsedDate.getTime())) {
      return parsedDate;
    }
  }

  return null;
}

function parseRomeLocalDateTime(value: string): Date | null {
  const match =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?/.exec(
      value.trim(),
    );
  if (!match) {
    return null;
  }

  const [, rawYear, rawMonth, rawDay, rawHour, rawMinute, rawSecond] = match;
  const utcGuess = Date.UTC(
    Number(rawYear),
    Number(rawMonth) - 1,
    Number(rawDay),
    Number(rawHour),
    Number(rawMinute),
    rawSecond ? Number(rawSecond) : 0,
  );
  const offsetMinutes = getTimeZoneOffsetMinutes(new Date(utcGuess));
  const parsedDate = new Date(utcGuess - offsetMinutes * 60_000);
  return Number.isNaN(parsedDate.getTime()) ? null : parsedDate;
}

async function resolveSolarTimeSync(): Promise<SolarTimeSyncState> {
  if (typeof window === "undefined" || typeof fetch === "undefined") {
    return { offsetMs: 0, source: "pc" };
  }

  for (const endpoint of SOLAR_TIME_ENDPOINTS) {
    try {
      const payload = await fetchJsonWithTimeout(endpoint, SOLAR_TIME_FETCH_TIMEOUT_MS);
      const internetDate = parseInternetTimePayload(payload);
      if (internetDate !== null) {
        return {
          offsetMs: internetDate.getTime() - Date.now(),
          source: "internet",
        };
      }
    } catch {
      // Se il device non ha internet, lo sfondo resta sincronizzato all'orologio locale.
    }
  }

  return { offsetMs: 0, source: "pc" };
}

function getSolarAmbientFrame(date = new Date()): SolarAmbientFrame {
  const romeParts = getRomeDateTimeParts(date);
  const minutes = romeParts.hour * 60 + romeParts.minute + romeParts.second / 60;
  const solarTimes = calculateAverageItalianSolarTimes(date);
  const solarAmbientPalette = buildSolarAmbientPalette(solarTimes);
  const nextIndex = solarAmbientPalette.findIndex((item) => item.minute >= minutes);
  const currentIndex = Math.max(0, nextIndex - 1);
  const current = solarAmbientPalette[currentIndex] ?? solarAmbientPalette[0]!;
  const next =
    solarAmbientPalette[nextIndex] ?? solarAmbientPalette[solarAmbientPalette.length - 1]!;
  const span = Math.max(1, next.minute - current.minute);
  const ratio = smoothStep((minutes - current.minute) / span);
  const sunWindowStart = solarTimes.sunriseMinute - 45;
  const sunWindowEnd = solarTimes.sunsetMinute + 45;
  const sunProgress = clampNumber(
    (minutes - sunWindowStart) / (sunWindowEnd - sunWindowStart),
    0,
    1,
  );
  const daylightArc = Math.sin(sunProgress * Math.PI);
  const sunVisible =
    minutes >= sunWindowStart && minutes <= sunWindowEnd ? smoothStep(daylightArc) : 0;

  return {
    skyTop: mixHexColor(current.skyTop, next.skyTop, ratio),
    skyMid: mixHexColor(current.skyMid, next.skyMid, ratio),
    skyBottom: mixHexColor(current.skyBottom, next.skyBottom, ratio),
    horizonGlow: ratio < 0.5 ? current.horizonGlow : next.horizonGlow,
    sunX: 4 + sunProgress * 92,
    sunY: 86 - daylightArc * 66,
    sunOpacity: sunVisible > 0 ? 0.16 + sunVisible * 0.54 : 0,
    sunScale: 0.96 + daylightArc * 0.18,
    sunTint:
      minutes < 540 || minutes > 1020
        ? "rgba(255, 187, 116, 0.92)"
        : "rgba(255, 245, 204, 0.86)",
  };
}

function readStoredSolarBackgroundEnabled(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  try {
    return window.localStorage.getItem(SOLAR_BACKGROUND_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

function resolvePowerHistoryPreset(presetId: PowerHistoryRangePresetId) {
  return (
    POWER_HISTORY_RANGE_PRESETS.find((candidate) => candidate.id === presetId) ??
    POWER_HISTORY_RANGE_PRESETS.find(
      (candidate) => candidate.id === DEFAULT_POWER_HISTORY_RANGE_PRESET,
    )!
  );
}

function buildPresetPowerHistoryRange(
  presetId: PowerHistoryRangePresetId,
  end = new Date(),
  isLive = true,
): PowerHistoryRangeSelection {
  const preset = resolvePowerHistoryPreset(presetId);
  const start = new Date(end.getTime() - preset.durationMs);

  return {
    presetId: preset.id,
    mode: "preset",
    startIso: start.toISOString(),
    endIso: end.toISOString(),
    isLive,
  };
}

function getPowerHistoryRangeDurationMs(range: PowerHistoryRangeSelection): number {
  return Math.max(60_000, new Date(range.endIso).getTime() - new Date(range.startIso).getTime());
}

function getPowerHistoryRangeMaxPoints(range: PowerHistoryRangeSelection): number {
  if (range.mode === "preset") {
    return resolvePowerHistoryPreset(range.presetId).maxPoints;
  }

  const durationMs = getPowerHistoryRangeDurationMs(range);
  const matchedPreset =
    POWER_HISTORY_RANGE_PRESETS.find((candidate) => candidate.durationMs >= durationMs) ??
    POWER_HISTORY_RANGE_PRESETS[POWER_HISTORY_RANGE_PRESETS.length - 1];
  return matchedPreset.maxPoints;
}

function buildPowerHistoryQuery(
  range: PowerHistoryRangeSelection,
  now = new Date(),
): PowerHistoryQuery {
  if (range.isLive && range.mode === "preset") {
    const liveRange = buildPresetPowerHistoryRange(range.presetId, now, true);
    return {
      start: liveRange.startIso,
      end: liveRange.endIso,
      max_points: getPowerHistoryRangeMaxPoints(liveRange),
    };
  }

  return {
    start: range.startIso,
    end: range.endIso,
    max_points: getPowerHistoryRangeMaxPoints(range),
  };
}

function getPowerHistoryRefreshMs(presetId: PowerHistoryRangePresetId): number {
  const preset = resolvePowerHistoryPreset(presetId);
  const dayMs = 24 * 60 * 60 * 1000;

  if (preset.durationMs >= 30 * dayMs) {
    return 120000;
  }
  if (preset.durationMs >= 7 * dayMs) {
    return 60000;
  }
  if (preset.durationMs >= dayMs) {
    return 30000;
  }
  return POWER_HISTORY_REFRESH_MS;
}

function formatCompactPowerKw(valueKw: number | null | undefined): string {
  if (valueKw === null || valueKw === undefined || !Number.isFinite(valueKw)) {
    return "--";
  }

  const absoluteValue = Math.abs(valueKw);
  if (absoluteValue >= 1_000_000) {
    return `${metricFormatter.format(valueKw / 1_000_000)} GW`;
  }
  if (absoluteValue >= 1_000) {
    return `${metricFormatter.format(valueKw / 1_000)} MW`;
  }
  return `${metricFormatter.format(valueKw)} kW`;
}

function formatStoredSetpointTimestamp(rawValue: string | null): string | null {
  if (!rawValue) {
    return null;
  }
  const parsed = new Date(rawValue);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return dateTimeFormatter.format(parsed);
}

function buildDeviceOverviewRefreshSignature(devices: Device[]): string {
  return devices.map((device) => `${device.device_id}:${device.status}`).join("|");
}

function formatRuntimeTimestamp(rawValue: string | null | undefined): string | null {
  if (!rawValue) {
    return null;
  }
  const parsed = new Date(rawValue);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return dateTimeFormatter.format(parsed);
}

function formatPercentValue(
  value: number | null | undefined,
  fractionDigits = 1,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "--";
  }

  return `${new Intl.NumberFormat("it-IT", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value)} %`;
}

function formatSignedPowerDeltaKw(valueKw: number | null | undefined): string {
  if (valueKw === null || valueKw === undefined || !Number.isFinite(valueKw)) {
    return "--";
  }

  const absoluteLabel = formatCompactPowerKw(Math.abs(valueKw));
  if (Math.abs(valueKw) < 0.05) {
    return `0,0 kW`;
  }
  return `${valueKw > 0 ? "+" : "-"}${absoluteLabel}`;
}

function translateControlConfidenceState(
  state: FleetControlConfidence["state"] | undefined,
): string {
  switch (state) {
    case "idle":
      return "In attesa";
    case "tracking":
      return "In invio";
    case "stable":
      return "Inviato";
    case "confirmed":
      return "Inviato";
    case "warning":
      return "Da verificare";
    default:
      return "Controllo";
  }
}

function translateReadinessStateLabel(
  state: FleetReadiness["overall_state"] | FleetReadinessCheck["state"] | undefined,
): string {
  switch (state) {
    case "pass":
      return "Pronto";
    case "warn":
      return "Da verificare";
    case "fail":
      return "Bloccante";
    default:
      return "Stato";
  }
}

function translateTimelineCategoryLabel(category: string): string {
  switch (category) {
    case "setpoint":
      return "Setpoint";
    case "dispatch":
      return "Dispatch";
    case "cci":
      return "CCI";
    case "polling":
      return "Lettura";
    case "hsm":
      return "Bridge HSM";
    default:
      return category;
  }
}

function buildControlConfidenceMessage(
  confidence: FleetControlConfidence | null | undefined,
): string {
  if (!confidence || confidence.requested_percent == null) {
    return "Nessun target globale attivo: il pannello si aggiorna appena arriva un nuovo setpoint.";
  }

  if (confidence.eligible_devices <= 0) {
    return "C'e un target attivo, ma la flotta non espone ancora inverter compatibili per ricevere il comando.";
  }

  if (confidence.state === "confirmed") {
    return "Il comando e stato inviato e la telemetria disponibile mostra gli inverter gia allineati sul target richiesto.";
  }

  if (confidence.state === "stable") {
    return "Il comando e stato inviato agli inverter compatibili nel ciclo corrente.";
  }

  if (confidence.state === "tracking") {
    return "Il target e attivo e il runtime sta completando l'invio del comando verso gli inverter.";
  }

  if (confidence.state === "warning") {
    return "Almeno un inverter e bloccato o in errore sul target: la dashboard evidenzia dove fermarsi a verificare.";
  }

  return "Il controllo flotta e pronto a inseguire il prossimo target utile.";
}

function buildTimelineEventHighlights(event: FleetTimelineEvent): string[] {
  const highlights = [translateTimelineCategoryLabel(event.category)];
  const requestedPercent = event.details.requested_percent;
  if (typeof requestedPercent === "number") {
    highlights.push(`Target ${formatPercentValue(requestedPercent)}`);
  }
  const referencePercent = event.details.reference_percent;
  if (typeof referencePercent === "number") {
    highlights.push(`Finestra ${formatPercentValue(referencePercent)}`);
  }
  const source = event.details.source;
  if (typeof source === "string" && source.trim().length > 0) {
    highlights.push(`Sorgente ${translateFleetSourceLabel(source)}`);
  }
  const activeSource = event.details.active_source;
  if (typeof activeSource === "string" && activeSource.trim().length > 0) {
    highlights.push(`Priorita ${translateFleetSourceLabel(activeSource)}`);
  }
  const port = event.details.port;
  if (typeof port === "string" && port.trim().length > 0) {
    highlights.push(port);
  }
  const pollKind = event.details.poll_kind;
  if (typeof pollKind === "string" && pollKind.trim().length > 0) {
    highlights.push(pollKind === "active_power" ? "Solo potenza attiva" : "Lettura completa");
  }
  return highlights.slice(0, 4);
}

function buildModbusSlaveSettingsDraft(
  fleetControl: FleetControlStatus | null,
): ModbusSlaveSettingsDraft | null {
  if (fleetControl === null) {
    return null;
  }

  return {
    enabled: fleetControl.modbus_tcp_slave.enabled,
    host: fleetControl.modbus_tcp_slave.host,
    port: String(fleetControl.modbus_tcp_slave.port),
    unitId: String(fleetControl.modbus_tcp_slave.unit_id),
    cciReadbackEnabled: fleetControl.modbus_tcp_slave.cci_readback_enabled,
    cciReadbackRangePercent: String(fleetControl.modbus_tcp_slave.cci_readback_range_percent),
    cciReadbackStableSeconds: String(fleetControl.modbus_tcp_slave.cci_readback_stable_seconds),
    cciReadbackActivePowerOnly: fleetControl.modbus_tcp_slave.cci_readback_active_power_only,
  };
}

function buildHsmBridgeSettingsDraft(
  fleetControl: FleetControlStatus | null,
): HsmBridgeSettingsDraft | null {
  if (fleetControl === null || !("hsm_bridge" in fleetControl)) {
    return null;
  }

  return {
    enabled: fleetControl.hsm_bridge.enabled,
    hsmPort: fleetControl.hsm_bridge.hsm_port,
    inverterPort: fleetControl.hsm_bridge.inverter_port,
    hsmBaudRate: String(fleetControl.hsm_bridge.hsm_baud_rate),
    hsmParity: fleetControl.hsm_bridge.hsm_parity,
    hsmStopBits: String(fleetControl.hsm_bridge.hsm_stop_bits),
    hsmByteSize: String(fleetControl.hsm_bridge.hsm_byte_size),
    frameGapMs: String(fleetControl.hsm_bridge.frame_gap_ms),
    forwardDelayMs: String(fleetControl.hsm_bridge.forward_delay_ms),
    ackTimeoutMs: String(fleetControl.hsm_bridge.ack_timeout_ms),
  };
}

function SettingsCardHint({ section }: { section: SettingsSectionAccent }) {
  const content = SETTINGS_SECTION_CONTENT[section];
  return (
    <div className="operator-settings-card__hint">
      <span className="operator-settings-card__hint-label">{content.menuHintLabel}</span>
      <p className="operator-settings-card__hint-copy">{content.menuHint}</p>
    </div>
  );
}

function SettingsGuidanceList({
  items,
  limit,
}: {
  items: SettingsGuidanceItem[];
  limit?: number;
}) {
  const visibleItems = typeof limit === "number" ? items.slice(0, limit) : items;
  return (
    <ul className="settings-guidance-list">
      {visibleItems.map((item) => (
        <li key={`${item.label}:${item.text}`}>
          <strong>{item.label}</strong>
          <span>{item.text}</span>
        </li>
      ))}
    </ul>
  );
}

function buildSerialPortChoices(
  serialPorts: SerialPortInfo[],
  currentValue: string,
): Array<{ value: string; label: string }> {
  const normalizedCurrentValue = currentValue.trim();
  const options = serialPorts.map((serialPort) => ({
    value: serialPort.name,
    label: buildSerialPortLabel(serialPort),
  }));

  if (
    normalizedCurrentValue &&
    !options.some((option) => option.value === normalizedCurrentValue)
  ) {
    options.unshift({
      value: normalizedCurrentValue,
      label: getSerialPortDisplayName(normalizedCurrentValue),
    });
  }

  return options;
}

type CompactTelemetryLookupDefinition = {
  keys: string[];
  terms: string[];
  units?: string[];
  excludeTerms?: string[];
};

function normalizeCompactTelemetryValue(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function normalizeCompactTelemetryUnit(unit: string): string {
  return normalizeCompactTelemetryValue(unit).replace(/\s+/g, "");
}

function countCompactTermHits(source: string, terms: string[]): number {
  return terms.reduce(
    (total, term) =>
      source.includes(normalizeCompactTelemetryValue(term)) ? total + 1 : total,
    0,
  );
}

function findCompactTelemetryPoint(
  overview: DeviceOverview | null,
  definition: CompactTelemetryLookupDefinition,
): DeviceOverviewTelemetryPoint | null {
  if (overview === null) {
    return null;
  }

  const visiblePoints = buildOrderedTelemetrySections(overview.telemetry).flatMap(
    (section) => section.points,
  );

  const rankedCandidates = visiblePoints
    .map((point) => {
      if (point.value === null || point.display_value.trim().length === 0) {
        return { point, score: Number.NEGATIVE_INFINITY };
      }

      const fingerprint = normalizeCompactTelemetryValue(
        `${point.key} ${point.label} ${point.section}`,
      );
      const normalizedUnit = normalizeCompactTelemetryUnit(point.unit);

      if (
        (definition.excludeTerms ?? []).some((term) =>
          fingerprint.includes(normalizeCompactTelemetryValue(term)),
        )
      ) {
        return { point, score: Number.NEGATIVE_INFINITY };
      }

      if (definition.units && definition.units.length > 0) {
        if (!point.unit || !definition.units.includes(normalizedUnit)) {
          return { point, score: Number.NEGATIVE_INFINITY };
        }
      }

      const exactKeyIndex = definition.keys.findIndex((candidate) => candidate === point.key);
      const termHits = countCompactTermHits(fingerprint, definition.terms);

      let score = 0;
      if (exactKeyIndex >= 0) {
        score += 1_000 - exactKeyIndex * 10;
      }
      if (termHits > 0) {
        score += termHits * 60;
      }

      return {
        point,
        score: score > 0 ? score : Number.NEGATIVE_INFINITY,
      };
    })
    .filter((candidate) => Number.isFinite(candidate.score))
    .sort((left, right) => right.score - left.score);

  return rankedCandidates[0]?.point ?? null;
}

function formatCompactTelemetryPoint(point: DeviceOverviewTelemetryPoint | null): string {
  if (point === null) {
    return "n.d.";
  }
  return point.unit ? `${point.display_value} ${point.unit}` : point.display_value;
}

const OPERATOR_COSPHI_LOOKUP: CompactTelemetryLookupDefinition = {
  keys: ["cos_phi", "power_factor", "actual_cosphi", "actual_cos_phi"],
  terms: ["cos(phi)", "cos phi", "cosphi", "power factor", "fattore di potenza"],
  excludeTerms: ["target", "reference", "setpoint", "meter", "contatore", "powermeter"],
};

const OPERATOR_TEMPERATURE_LOOKUP: CompactTelemetryLookupDefinition = {
  keys: [
    "temperature_c",
    "internal_temperature_c",
    "inside_temperature_c",
    "heat_sink_temperature_c",
    "inner_temperature_c",
    "control_temperature_c",
    "control_board_temperature_c",
  ],
  terms: ["temperatura", "temperature", "heat sink", "dissipatore", "interna"],
  units: ["c"],
  excludeTerms: ["fault", "warning", "alarm", "allarme", "min", "max"],
};

const OPERATOR_TOTAL_ENERGY_LOOKUP: CompactTelemetryLookupDefinition = {
  keys: [
    "total_energy_kwh",
    "total_energy",
    "total_yield_wh",
    "generation_energy_wh",
    "lifetime_energy_kwh",
    "total_energy_decikwh",
  ],
  terms: ["energia totale", "total energy", "lifetime energy", "total yield", "energia cumulata"],
  units: ["kwh", "wh", "mwh"],
  excludeTerms: [
    "daily",
    "giornal",
    "oggi",
    "yesterday",
    "ieri",
    "resettable",
    "meter",
    "contatore rete",
  ],
};

function LanIcon() {
  return (
    <svg
      aria-hidden="true"
      className="button-icon-svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M6 4.5h12a1.5 1.5 0 0 1 1.5 1.5v7a1.5 1.5 0 0 1-1.5 1.5H15.5v2.25l-1.5-1-1.5 1-1.5-1-1.5 1V14.5H6A1.5 1.5 0 0 1 4.5 13V6A1.5 1.5 0 0 1 6 4.5Z" />
      <path d="M8 8.25h8" />
      <path d="M8 11.25h1.5" />
      <path d="M11.25 11.25h1.5" />
      <path d="M14.5 11.25H16" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg
      aria-hidden="true"
      className="button-icon-svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 8.5a3.5 3.5 0 1 1 0 7a3.5 3.5 0 0 1 0-7Z" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .35 1.9l.05.05a2 2 0 0 1-2.83 2.83l-.05-.05a1.7 1.7 0 0 0-1.9-.35a1.7 1.7 0 0 0-1.02 1.55V21a2 2 0 0 1-4 0v-.07a1.7 1.7 0 0 0-1.02-1.55a1.7 1.7 0 0 0-1.9.35l-.05.05a2 2 0 1 1-2.83-2.83l.05-.05A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1.02H3a2 2 0 0 1 0-4h.05A1.7 1.7 0 0 0 4.6 8a1.7 1.7 0 0 0-.35-1.9l-.05-.05a2 2 0 1 1 2.83-2.83l.05.05a1.7 1.7 0 0 0 1.9.35A1.7 1.7 0 0 0 10 2.07V2a2 2 0 0 1 4 0v.07a1.7 1.7 0 0 0 1.02 1.55a1.7 1.7 0 0 0 1.9-.35l.05-.05a2 2 0 1 1 2.83 2.83l-.05.05A1.7 1.7 0 0 0 19.4 8a1.7 1.7 0 0 0 1.55 1.98H21a2 2 0 0 1 0 4h-.05A1.7 1.7 0 0 0 19.4 15Z" />
    </svg>
  );
}

function Rj45Icon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M7 4.5h10l2 2v5l-3 3H8l-3-3v-5l2-2Z" />
      <path d="M9 8.5h1" />
      <path d="M12 8.5h1" />
      <path d="M15 8.5h1" />
      <path d="M10 14.5v3" />
      <path d="M14 14.5v3" />
      <path d="M8 20h8" />
    </svg>
  );
}

function ProvisioningIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="4.5" y="5" width="9" height="14" rx="2" />
      <path d="M8 9.5h2" />
      <path d="M8 13.5h2" />
      <path d="M16.5 9v7" />
      <path d="M13 12.5h7" />
    </svg>
  );
}

function HealthPulseIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3.5 12h4l2-3 3 7 2.5-4H20.5" />
      <path d="M6 6.5h12" opacity="0.45" />
      <path d="M6 17.5h12" opacity="0.45" />
    </svg>
  );
}

function HistoryChartIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4.5 18.5h15" />
      <path d="M7.5 15.5V11" />
      <path d="M12 15.5V7.5" />
      <path d="M16.5 15.5v-5" />
      <path d="M6.5 7.5 10 5l3 2 4.5-2" />
    </svg>
  );
}

function DashboardGridIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="4.5" y="5" width="6.5" height="6.5" rx="1.5" />
      <rect x="13" y="5" width="6.5" height="4.5" rx="1.5" />
      <rect x="13" y="11.5" width="6.5" height="7.5" rx="1.5" />
      <rect x="4.5" y="13.5" width="6.5" height="5.5" rx="1.5" />
    </svg>
  );
}

function SolarBackgroundIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 17.5h16" opacity="0.5" />
      <path d="M7 17.5a5 5 0 0 1 10 0" />
      <path d="M12 4v2.5" />
      <path d="M5.8 7.1l1.8 1.8" />
      <path d="M18.2 7.1l-1.8 1.8" />
      <path d="M3.8 12.8h2.5" opacity="0.65" />
      <path d="M17.7 12.8h2.5" opacity="0.65" />
    </svg>
  );
}

function ControlAuditIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 5.5h6.5v6.5H5z" />
      <path d="M12.5 8.75H19" />
      <path d="M16 5.75 19 8.75 16 11.75" />
      <path d="M19 18.5h-6.5V12H19z" />
      <path d="M11.5 15.25H5" />
      <path d="M8 12.25 5 15.25 8 18.25" />
    </svg>
  );
}

function SlaveBridgeIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="4.5" y="6" width="6.5" height="12" rx="1.8" />
      <rect x="13" y="6" width="6.5" height="12" rx="1.8" />
      <path d="M11 12h2" />
      <path d="M7 9.5h1.5" />
      <path d="M7 12h1.5" />
      <path d="M7 14.5h1.5" />
      <path d="M15.5 9.5H17" />
      <path d="M15.5 12H17" />
      <path d="M15.5 14.5H17" />
    </svg>
  );
}

function HsmBridgeIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3.5" y="6" width="6.5" height="12" rx="1.7" />
      <rect x="14" y="6" width="6.5" height="12" rx="1.7" />
      <path d="M10 12h4" />
      <path d="M6 9.5h1.5" />
      <path d="M6 12h1.5" />
      <path d="M6 14.5h1.5" />
      <path d="M16.5 9.5H18" />
      <path d="M16.5 12H18" />
      <path d="M16.5 14.5H18" />
    </svg>
  );
}

function DashboardModeSwitch({
  mode,
  onChange,
}: {
  mode: DashboardMode;
  onChange: (mode: DashboardMode) => void;
}) {
  return (
    <div className="dashboard-mode-switch" role="tablist" aria-label="Modalita dashboard">
      <button
        className={`dashboard-mode-switch__button ${
          mode === "operator" ? "dashboard-mode-switch__button--active" : ""
        }`}
        type="button"
        role="tab"
        aria-selected={mode === "operator"}
        onClick={() => onChange("operator")}
      >
        Operatore
      </button>
      <button
        className={`dashboard-mode-switch__button ${
          mode === "lite" ? "dashboard-mode-switch__button--active" : ""
        }`}
        type="button"
        role="tab"
        aria-selected={mode === "lite"}
        onClick={() => onChange("lite")}
      >
        Lite
      </button>
      <button
        className={`dashboard-mode-switch__button ${
          mode === "pro" ? "dashboard-mode-switch__button--active" : ""
        }`}
        type="button"
        role="tab"
        aria-selected={mode === "pro"}
        onClick={() => onChange("pro")}
      >
        Pro
      </button>
    </div>
  );
}

function SolarAmbientBackground({ enabled }: { enabled: boolean }) {
  const [frame, setFrame] = useState(() => getSolarAmbientFrame());
  const [timeSync, setTimeSync] = useState<SolarTimeSyncState>({
    offsetMs: 0,
    source: "pc",
  });

  useEffect(() => {
    if (!enabled || typeof window === "undefined") {
      return;
    }

    let cancelled = false;
    async function syncInternetTime() {
      const nextTimeSync = await resolveSolarTimeSync();
      if (!cancelled) {
        setTimeSync(nextTimeSync);
      }
    }

    void syncInternetTime();
    const intervalId = window.setInterval(() => {
      void syncInternetTime();
    }, SOLAR_TIME_RESYNC_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [enabled]);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") {
      return;
    }

    function updateFrame() {
      setFrame(getSolarAmbientFrame(new Date(Date.now() + timeSync.offsetMs)));
    }

    updateFrame();
    const intervalId = window.setInterval(() => {
      updateFrame();
    }, SOLAR_BACKGROUND_UPDATE_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [enabled, timeSync.offsetMs]);

  if (!enabled) {
    return null;
  }

  const style = {
    "--solar-sky-top": frame.skyTop,
    "--solar-sky-mid": frame.skyMid,
    "--solar-sky-bottom": frame.skyBottom,
    "--solar-horizon-glow": frame.horizonGlow,
    "--solar-sun-x": `${frame.sunX}%`,
    "--solar-sun-y": `${frame.sunY}%`,
    "--solar-sun-opacity": String(frame.sunOpacity),
    "--solar-sun-scale": String(frame.sunScale),
    "--solar-sun-tint": frame.sunTint,
  } as CSSProperties;

  return (
    <div className="solar-ambient-background" style={style} aria-hidden="true">
      <div className="solar-ambient-background__sun" />
      <div className="solar-ambient-background__horizon" />
      <div className="solar-ambient-background__overlay" />
    </div>
  );
}

function buildPlantPowerComparison(summary: DashboardSummary | null): {
  comparison: string;
  coverage: string;
  utilizationPercent: number | null;
} {
  if (summary === null) {
    return {
      comparison: "Confronto nominale non disponibile.",
      coverage: "Copertura nominale non disponibile.",
      utilizationPercent: null,
    };
  }

  if (summary.nominal_power_kw <= 0) {
    return {
      comparison: "Potenza nominale AC non ancora disponibile.",
      coverage:
        summary.total_devices > 0
          ? `Nominale rilevata su ${summary.nominal_power_device_count}/${summary.total_devices} dispositivi.`
          : "Nessun dispositivo configurato.",
      utilizationPercent: null,
    };
  }

  const comparison = `${formatCompactPowerKw(summary.total_power_kw)} su ${formatCompactPowerKw(summary.nominal_power_kw)} nominali`;
  const coverage =
    summary.nominal_power_device_count >= summary.total_devices
      ? "Nominale AC installata completa."
      : `Nominale rilevata su ${summary.nominal_power_device_count}/${summary.total_devices} dispositivi.`;

  return {
    comparison,
    coverage,
    utilizationPercent: summary.power_utilization_percent,
  };
}

function buildLiteHeroMessage(
  summary: DashboardSummary | null,
  loading: boolean,
  hasError: boolean,
  systemHealthHasAttention: boolean,
): { title: string; note: string; tone: SummaryTone } {
  if (loading) {
    return {
      title: "Sincronizzazione dashboard",
      note: "Sto aggiornando stato impianto, potenza e disponibilita dagli inverter.",
      tone: "neutral",
    };
  }

  if (hasError) {
    return {
      title: "Monitoraggio momentaneamente non disponibile",
      note: "Il frontend non ha ricevuto dati validi dal backend nell'ultimo aggiornamento.",
      tone: "warning",
    };
  }

  if (summary === null || summary.total_devices <= 0) {
    return {
      title: "Nessun inverter configurato",
      note: "Aggiungi o importa i dispositivi per popolare la dashboard semplificata.",
      tone: "neutral",
    };
  }

  if (systemHealthHasAttention) {
    return {
      title: "Impianto operativo con elementi da verificare",
      note: "La produzione e monitorata, ma almeno un inverter o un endpoint richiede attenzione.",
      tone: "warning",
    };
  }

  return {
    title: "Impianto monitorato regolarmente",
    note: "Produzione, disponibilita e allarmi risultano sotto controllo nell'ultimo ciclo utile.",
    tone: "positive",
  };
}

function buildLiteSelectedSummaryItems(
  device: Device,
  overview: DeviceOverview | null,
): SummaryItem[] {
  return [
    {
      label: "Stato dispositivo",
      value: translateStatusLabel(device.status),
      caption: "Esito ultimo ciclo di comunicazione disponibile",
      tone: getStatusTone(device.status),
    },
    {
      label: "Potenza attuale",
      value: overview ? `${metricFormatter.format(overview.metrics.power_kw)} kW` : "--",
      caption: "Produzione attiva dell'inverter nell'ultimo polling utile",
      tone: "positive",
    },
    {
      label: "Energia oggi",
      value: overview ? `${metricFormatter.format(overview.metrics.daily_energy_kwh)} kWh` : "--",
      caption: "Produzione giornaliera del dispositivo",
      tone: "neutral",
    },
    {
      label: "Energia totale",
      value: overview ? `${metricFormatter.format(overview.metrics.total_energy_kwh)} kWh` : "--",
      caption: "Contatore cumulato disponibile sul modello",
      tone: "neutral",
    },
  ];
}

function getLiteDevicePriority(status: string): number {
  switch (status.toLowerCase()) {
    case "fault":
      return 0;
    case "warning":
      return 1;
    case "offline":
      return 2;
    case "pending":
      return 3;
    case "degraded":
      return 4;
    case "online":
      return 5;
    default:
      return 6;
  }
}

function buildLiteDeviceCondition(status: string): string {
  switch (status.toLowerCase()) {
    case "online":
      return "Monitoraggio regolare";
    case "degraded":
      return "Contatto presente, dati da consolidare";
    case "pending":
      return "In attesa del primo dato utile";
    case "warning":
      return "Richiede una verifica operativa";
    case "fault":
      return "Guasto o allarme da verificare";
    case "offline":
      return "Comunicazione assente";
    default:
      return "Stato da verificare";
  }
}

function LiteDeviceCard({
  device,
  currentPower,
  onOpenPro,
}: {
  device: Device;
  currentPower: number | null | undefined;
  onOpenPro: () => void;
}) {
  return (
    <article className="lite-device-card">
      <div className="lite-device-card__head">
        <div>
          <p className="lite-device-card__name">{device.name}</p>
          <p className="lite-device-card__caption">
            {device.brand} | {device.model}
          </p>
        </div>
        <StatusBadge status={device.status} />
      </div>
      <div className="lite-device-card__body">
        <div>
          <p className="lite-device-card__label">Potenza attuale</p>
          <strong className="lite-device-card__power">{formatSidebarPower(currentPower)}</strong>
        </div>
        <div>
          <p className="lite-device-card__label">Condizione</p>
          <p className="lite-device-card__caption">
            {buildLiteDeviceCondition(device.status)}
          </p>
        </div>
      </div>
      <div className="lite-device-card__actions">
        <button className="secondary-button" type="button" onClick={onOpenPro}>
          Apri in Pro
        </button>
      </div>
    </article>
  );
}

function getOperatorGridPageSize(viewportWidth: number, deviceCount: number): number {
  if (deviceCount <= 4) {
    return 4;
  }
  if (viewportWidth >= 1680) {
    return 12;
  }
  if (viewportWidth >= 1360) {
    return 10;
  }
  return 8;
}

function OperatorServiceMenu({
  open,
  attention,
  selectedDevice,
  onToggle,
  onOpenSettingsPage,
  onOpenPro,
  onOpenHistory,
}: {
  open: boolean;
  attention: boolean;
  selectedDevice: Device | null;
  onToggle: () => void;
  onOpenSettingsPage: () => void;
  onOpenPro: () => void;
  onOpenHistory: () => void;
}) {
  return (
    <div className="operator-service-menu">
      <button
        className={`secondary-button operator-service-menu__trigger ${
          attention ? "operator-service-menu__trigger--attention" : ""
        }`}
        type="button"
        onClick={onToggle}
      >
        <span>Servizi</span>
        {attention ? <span className="operator-service-menu__indicator" aria-hidden="true" /> : null}
      </button>
      {open ? (
        <div className="operator-service-menu__panel">
          <button className="operator-service-menu__item" type="button" onClick={onOpenSettingsPage}>
            Impostazioni
          </button>
          <button className="operator-service-menu__item" type="button" onClick={onOpenPro}>
            {selectedDevice ? "Dettaglio tecnico" : "Dashboard Pro"}
          </button>
          <button className="operator-service-menu__item" type="button" onClick={onOpenHistory}>
            Storico avanzato
          </button>
        </div>
      ) : null}
    </div>
  );
}

function OperatorSummaryCard({
  label,
  value,
  note,
  tone = "neutral",
  className = "",
  children,
}: {
  label: string;
  value: string;
  note: string;
  tone?: SummaryTone;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <article className={`operator-summary-card operator-summary-card--${tone} ${className}`}>
      <span className="operator-summary-card__label">{label}</span>
      <strong className="operator-summary-card__value">{value}</strong>
      <p className="operator-summary-card__note">{note}</p>
      {children ? <div className="operator-summary-card__body">{children}</div> : null}
    </article>
  );
}

function OperatorPlantControlCard({
  loading,
  powerValue,
  caption,
  inputValue,
  actionBusy,
  actionError,
  onInputChange,
  onApply,
  onClear,
}: {
  loading: boolean;
  powerValue: string;
  caption: string;
  inputValue: string;
  actionBusy: boolean;
  actionError: string | null;
  onInputChange: (value: string) => void;
  onApply: () => void;
  onClear: () => void;
}) {
  return (
    <OperatorSummaryCard
      label="Potenza impianto"
      value={loading ? "Caricamento..." : powerValue}
      note={caption}
      tone="positive"
    >
      <div className="operator-summary-card__command-strip">
        <span className="operator-summary-card__command-label">Setpoint manuale</span>
        <div className="operator-summary-card__command-controls">
          <input
            className="field-control operator-summary-card__input"
            type="number"
            min={0}
            max={100}
            step={1}
            value={inputValue}
            onChange={(event) => {
              const nextValue = event.currentTarget.value;
              onInputChange(nextValue);
            }}
            disabled={actionBusy}
            placeholder="0-100"
            aria-label="Setpoint impianto percentuale"
          />
          <button
            className="secondary-button"
            type="button"
            onClick={onClear}
            disabled={actionBusy}
          >
            {actionBusy ? "Attendi..." : "Azzera"}
          </button>
          <button
            className="action-button"
            type="button"
            onClick={onApply}
            disabled={actionBusy}
          >
            {actionBusy ? "Applicazione..." : "Applica"}
          </button>
        </div>
      </div>
      {actionError ? (
        <p className="operator-summary-card__feedback operator-summary-card__feedback--error">
          {actionError}
        </p>
      ) : null}
    </OperatorSummaryCard>
  );
}

function OperatorControlConfidencePanel({
  fleetControl,
}: {
  fleetControl: FleetControlStatus | null;
}) {
  const confidence = fleetControl?.control_confidence ?? null;
  const requestedPercent = confidence?.requested_percent ?? null;
  const writtenPercent = confidence?.written_percent ?? null;
  const confirmedPercent = confidence?.confirmed_percent ?? null;
  const nominalPowerKw = confidence?.nominal_power_kw ?? null;
  const actualPowerKw = confidence?.actual_power_kw ?? null;
  const theoreticalTargetKw =
    requestedPercent !== null && nominalPowerKw !== null
      ? (nominalPowerKw * requestedPercent) / 100
      : null;
  const deltaPowerKw =
    actualPowerKw !== null && theoreticalTargetKw !== null
      ? actualPowerKw - theoreticalTargetKw
      : null;
  const confidenceState = confidence?.state ?? "idle";
  const lastTargetAt = formatRuntimeTimestamp(confidence?.last_target_at);
  const lastWriteAt = formatRuntimeTimestamp(confidence?.last_write_at);
  const lastConfirmationAt = formatRuntimeTimestamp(confidence?.last_confirmation_at);

  return (
    <section className="stage-panel operator-confidence-panel">
      <div className="stage-header">
        <div>
          <p className="panel-kicker">Controllo potenza</p>
          <h2>Invio del target impianto</h2>
          <p className="stage-copy">
            Qui verifichiamo se la richiesta e stata inviata agli inverter; il feedback telemetrico
            resta disponibile come supporto quando arriva il polling.
          </p>
        </div>
        <span className="panel-meta">
          {translateControlConfidenceState(confidenceState)}
        </span>
      </div>

      <div className="operator-confidence-layout">
        <article
          className={`operator-confidence-hero operator-confidence-hero--${confidenceState}`}
        >
          <div className="operator-confidence-hero__top">
            <span className={`operator-confidence-badge operator-confidence-badge--${confidenceState}`}>
              {translateControlConfidenceState(confidenceState)}
            </span>
            <span className="operator-confidence-hero__timestamp">
              {lastTargetAt ? `Ultimo target ${lastTargetAt}` : "In attesa del primo target"}
            </span>
          </div>

          <div className="operator-confidence-steps" aria-label="Stato target impianto">
            <div className="operator-confidence-step">
              <span>Richiesto</span>
              <strong>{formatPercentValue(requestedPercent)}</strong>
              <small>Valore sorgente attivo</small>
            </div>
            <div className="operator-confidence-step">
              <span>Inviato</span>
              <strong>{formatPercentValue(writtenPercent)}</strong>
              <small>
                {lastWriteAt ? `Ultimo invio ${lastWriteAt}` : "Nessun invio utile"}
              </small>
            </div>
          </div>

          <p className="operator-confidence-hero__message">
            {buildControlConfidenceMessage(confidence)}
          </p>
        </article>

        <div className="operator-confidence-stats">
          <article className="operator-confidence-stat">
            <span>Potenza reale</span>
            <strong>{formatCompactPowerKw(actualPowerKw)}</strong>
            <small>
              {confidence?.utilization_percent != null
                ? `${metricFormatter.format(confidence.utilization_percent)}% della nominale`
                : "Utilizzo nominale non disponibile"}
            </small>
          </article>
          <article className="operator-confidence-stat">
            <span>Scostamento</span>
            <strong>{formatSignedPowerDeltaKw(deltaPowerKw)}</strong>
            <small>
              {theoreticalTargetKw !== null
                ? `Riferimento teorico ${formatCompactPowerKw(theoreticalTargetKw)}`
                : "Target teorico non calcolabile"}
            </small>
          </article>
          <article className="operator-confidence-stat">
            <span>Inviati</span>
            <strong>
              {confidence ? `${confidence.aligned_devices}/${confidence.eligible_devices}` : "--"}
            </strong>
            <small>
              {confidence
                ? `${confidence.pending_devices} in invio | ${confidence.error_devices} con errore`
                : "Nessun controllo dispositivo disponibile"}
            </small>
          </article>
          <article className="operator-confidence-stat">
            <span>Feedback telemetrico</span>
            <strong>
              {confidence
                ? `${confidence.telemetry_confirmed_devices}/${confidence.eligible_devices}`
                : "--"}
            </strong>
            <small>
              {confidence
                ? lastConfirmationAt
                  ? `Ultimo feedback ${lastConfirmationAt}`
                  : confirmedPercent != null
                    ? `Ultimo valore letto ${formatPercentValue(confirmedPercent)}`
                    : "Disponibile appena il polling aggiorna i registri"
                : "Conferma telemetrica non disponibile"}
            </small>
          </article>
        </div>
      </div>
    </section>
  );
}

function OperatorCommissioningReadinessPanel({
  fleetControl,
  onOpenSettingsPage,
}: {
  fleetControl: FleetControlStatus | null;
  onOpenSettingsPage: () => void;
}) {
  const readiness = fleetControl?.readiness ?? null;
  const overallState = readiness?.overall_state ?? "warn";
  const overallLabel =
    overallState === "pass"
      ? "Impianto pronto al commissioning"
      : overallState === "fail"
        ? "C'e almeno un blocco da sciogliere"
        : "Impianto quasi pronto, con verifiche aperte";

  return (
    <section className="stage-panel operator-readiness-panel">
      <div className="stage-header">
        <div>
          <p className="panel-kicker">Commissioning</p>
          <h2>Readiness check</h2>
          <p className="stage-copy">
            Qui concentriamo le verifiche che servono davvero prima di fidarsi della regolazione
            in campo: flotta, CCI, polling, bridge HSM e linee seriali.
          </p>
        </div>
        <div className="stage-header-actions">
          <button className="secondary-button" type="button" onClick={onOpenSettingsPage}>
            Apri impostazioni
          </button>
        </div>
      </div>

      <div className="operator-readiness-summary">
        <article className={`operator-readiness-hero operator-readiness-hero--${overallState}`}>
          <span className={`operator-readiness-badge operator-readiness-badge--${overallState}`}>
            {translateReadinessStateLabel(overallState)}
          </span>
          <strong>{overallLabel}</strong>
          <p>
            {readiness
              ? `${readiness.ready_count} pronti | ${readiness.warning_count} da verificare | ${readiness.fail_count} bloccanti`
              : "Lo snapshot readiness comparira appena il backend restituisce lo stato completo della flotta."}
          </p>
        </article>

        <div className="operator-readiness-counts">
          <span className="operator-readiness-count operator-readiness-count--pass">
            {readiness?.ready_count ?? 0} pronti
          </span>
          <span className="operator-readiness-count operator-readiness-count--warn">
            {readiness?.warning_count ?? 0} da verificare
          </span>
          <span className="operator-readiness-count operator-readiness-count--fail">
            {readiness?.fail_count ?? 0} bloccanti
          </span>
        </div>
      </div>

      <div className="operator-readiness-list">
        {readiness?.checks.length ? (
          readiness.checks.map((check) => (
            <article
              key={check.key}
              className={`operator-readiness-item operator-readiness-item--${check.state}`}
            >
              <div className="operator-readiness-item__head">
                <strong>{check.label}</strong>
                <span className={`operator-readiness-badge operator-readiness-badge--${check.state}`}>
                  {translateReadinessStateLabel(check.state)}
                </span>
              </div>
              <p className="operator-readiness-item__summary">{check.summary}</p>
              <p className="operator-readiness-item__detail">{check.detail}</p>
            </article>
          ))
        ) : (
          <div className="operator-timeline-empty">
            Nessun controllo di readiness disponibile in questo momento.
          </div>
        )}
      </div>
    </section>
  );
}

function OperatorTimelinePanel({
  fleetControl,
  onOpenHistory,
}: {
  fleetControl: FleetControlStatus | null;
  onOpenHistory: () => void;
}) {
  const events = fleetControl?.timeline_events ?? [];

  return (
    <section className="stage-panel operator-timeline-panel">
      <div className="stage-header">
        <div>
          <p className="panel-kicker">Timeline impianto</p>
          <h2>Ultimi eventi operativi</h2>
          <p className="stage-copy">
            Uno storico corto ma vivo: setpoint, dispatch, letture CCI e bridge HSM, cosi si
            capisce in che ordine sono successe le cose.
          </p>
        </div>
        <div className="stage-header-actions">
          <button className="secondary-button" type="button" onClick={onOpenHistory}>
            Apri storico
          </button>
        </div>
      </div>

      <div className="operator-timeline-list">
        {events.length > 0 ? (
          events.map((event) => {
            const eventTimestamp = formatRuntimeTimestamp(event.timestamp) ?? event.timestamp;
            const highlights = buildTimelineEventHighlights(event);
            return (
              <article
                key={event.event_id}
                className={`operator-timeline-item operator-timeline-item--${event.level}`}
              >
                <span className="operator-timeline-item__dot" aria-hidden="true" />
                <div className="operator-timeline-item__body">
                  <div className="operator-timeline-item__head">
                    <strong>{event.title}</strong>
                    <span>{eventTimestamp}</span>
                  </div>
                  <p className="operator-timeline-item__message">{event.message}</p>
                  <div className="operator-timeline-item__chips">
                    {highlights.map((item) => (
                      <span key={`${event.event_id}:${item}`} className="operator-timeline-chip">
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
              </article>
            );
          })
        ) : (
          <div className="operator-timeline-empty">
            La timeline si popola appena arrivano eventi operativi dal runtime.
          </div>
        )}
      </div>
    </section>
  );
}

function OperatorProvisioningPageAlert({
  progress,
  busy,
  onCancel,
  onDismiss,
}: {
  progress: OperatorProvisioningProgressState;
  busy: boolean;
  onCancel: () => void;
  onDismiss: () => void;
}) {
  const progressPercent =
    progress.total > 0 ? Math.round((progress.completed / progress.total) * 100) : 0;
  const failedItems = progress.items.filter((item) => item.status === "error");
  const hasErrors = failedItems.length > 0;
  const headline = busy
    ? progress.currentName
      ? `Configurazione in corso: ${progress.currentName}`
      : "Configurazione dispositivi in corso"
    : hasErrors
      ? "Configurazione completata con avvisi"
      : "Configurazione completata";
  const caption = busy
    ? "Puoi chiudere il menu: il batch resta controllabile da qui."
    : hasErrors
      ? `${failedItems.length} dispositivi richiedono verifica.`
      : "Tutti i dispositivi selezionati sono stati elaborati.";

  return (
    <section
      className={`operator-provision-progress operator-provision-progress--global ${
        hasErrors ? "operator-provision-progress--error" : ""
      }`}
      role={hasErrors ? "alert" : "status"}
    >
      <div className="operator-provision-progress__head">
        <div>
          <p className="panel-kicker">Configurazione slave</p>
          <strong>{headline}</strong>
          <p className="operator-provision-progress__caption">{caption}</p>
        </div>
        <div className="operator-provision-progress__actions">
          <span>{progressPercent}%</span>
          {busy ? (
            <button className="danger-outline-button" type="button" onClick={onCancel}>
              Blocca
            </button>
          ) : (
            <button className="chip-inline-button" type="button" onClick={onDismiss}>
              Chiudi
            </button>
          )}
        </div>
      </div>
      <div className="operator-provision-progress__track" aria-hidden="true">
        <span style={{ width: `${progressPercent}%` }} />
      </div>
      <div className="operator-provision-progress__summary">
        <span>
          {progress.completed}/{progress.total} elaborati
        </span>
        {progress.currentName ? <span>In lavorazione: {progress.currentName}</span> : null}
        {hasErrors ? <span>{failedItems.length} errori</span> : null}
      </div>
      {hasErrors ? (
        <div className="operator-provision-progress__error-list">
          {failedItems.slice(0, 3).map((item) => (
            <p key={item.key}>
              <strong>{item.name}</strong>: {item.message}
            </p>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function OperatorFirstConnectAlert({
  watch,
  devices,
  overviewMap,
  onDismiss,
}: {
  watch: FirstConnectWatchState;
  devices: Device[];
  overviewMap: DeviceOverviewMap;
  onDismiss: () => void;
}) {
  const deviceById = new Map(devices.map((device) => [device.device_id, device]));
  const connectedTargets = watch.targets.filter((target) => {
    const device = deviceById.get(target.deviceId);
    const overview = overviewMap[target.deviceId] ?? null;
    return (
      overview?.diagnostics.last_contact_at != null ||
      overview?.diagnostics.communication_state === "online" ||
      device?.status === "online"
    );
  });
  const pendingTargets = watch.targets.filter(
    (target) => !connectedTargets.some((connected) => connected.deviceId === target.deviceId),
  );
  const connectedCount = connectedTargets.length;
  const totalCount = watch.targets.length;
  const progressPercent = totalCount > 0 ? Math.round((connectedCount / totalCount) * 100) : 100;
  const completed = totalCount > 0 && connectedCount >= totalCount;
  const elapsedSeconds = Math.max(0, Math.round((Date.now() - watch.startedAt) / 1000));
  const headline = completed
    ? "Primo connect completato"
    : "Connessione nuovi dispositivi in corso";
  const caption = completed
    ? "Tutti i dispositivi appena configurati hanno avuto il primo contatto con il backend."
    : "I device sono stati creati: il polling li sta agganciando uno alla volta e la dashboard si popola appena arrivano i primi dati.";

  return (
    <section
      className={`operator-provision-progress operator-provision-progress--global operator-provision-progress--connect ${
        completed ? "operator-provision-progress--connect-ready" : ""
      }`}
      role="status"
    >
      <div className="operator-provision-progress__head">
        <div>
          <p className="panel-kicker">Primo connect</p>
          <strong>{headline}</strong>
          <p className="operator-provision-progress__caption">{caption}</p>
        </div>
        <div className="operator-provision-progress__actions">
          <span>{progressPercent}%</span>
          {completed ? (
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
          {connectedCount}/{totalCount} connessi
        </span>
        <span>{elapsedSeconds}s dal salvataggio</span>
        {!completed && pendingTargets.length > 0 ? (
          <span>In attesa: {pendingTargets.slice(0, 3).map((target) => target.name).join(", ")}</span>
        ) : null}
      </div>
    </section>
  );
}

function NetworkPendingChangeAlert({
  pendingChange,
  busyAction,
  error,
  onConfirm,
  onRollback,
}: {
  pendingChange: PendingNetworkChange;
  busyAction: "confirm" | "rollback" | null;
  error: string | null;
  onConfirm: () => void;
  onRollback: () => void;
}) {
  const expiresAt = formatRuntimeTimestamp(pendingChange.expires_at) ?? pendingChange.expires_at;

  return (
    <section
      className={`operator-provision-progress operator-provision-progress--global operator-provision-progress--network ${
        error ? "operator-provision-progress--error" : ""
      }`}
      role={error ? "alert" : "status"}
    >
      <div className="operator-provision-progress__head">
        <div>
          <p className="panel-kicker">LAN Settings</p>
          <strong>Conferma modifica su {pendingChange.interface_name}</strong>
          <p className="operator-provision-progress__caption">
            Conferma dalla pagina principale entro {pendingChange.remaining_seconds} s. Scadenza:{" "}
            {expiresAt}.
          </p>
        </div>
        <div className="operator-provision-progress__actions">
          <span>{pendingChange.remaining_seconds}s</span>
          <div className="operator-provision-progress__button-row">
            <button
              className="secondary-button"
              type="button"
              onClick={onRollback}
              disabled={busyAction !== null}
            >
              {busyAction === "rollback" ? "Ripristino..." : "Rollback"}
            </button>
            <button
              className="action-button"
              type="button"
              onClick={onConfirm}
              disabled={busyAction !== null}
            >
              {busyAction === "confirm" ? "Conferma..." : "Conferma"}
            </button>
          </div>
        </div>
      </div>
      <div className="operator-provision-progress__track" aria-hidden="true">
        <span
          style={{
            width: `${Math.max(4, Math.min(100, pendingChange.remaining_seconds))}%`,
          }}
        />
      </div>
      {error ? (
        <div className="operator-provision-progress__error-list">
          <p>{error}</p>
        </div>
      ) : null}
    </section>
  );
}

function OperatorDeviceTile({
  active,
  device,
  overview,
  currentPower,
  deleteBusy,
  onSelect,
  onEdit,
  onDelete,
}: {
  active: boolean;
  device: Device;
  overview: DeviceOverview | null;
  currentPower: number | null | undefined;
  deleteBusy: boolean;
  onSelect: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const lastReadingAt = formatRuntimeTimestamp(overview?.diagnostics.last_contact_at);
  return (
    <article
      className={`operator-device-tile ${active ? "operator-device-tile--active" : ""}`}
    >
      <button className="operator-device-tile__main" type="button" onClick={onSelect}>
        <div className="operator-device-tile__head">
          <strong className="operator-device-tile__name">{device.name}</strong>
          <StatusBadge status={device.status} />
        </div>
        <span className="operator-device-tile__caption">{device.brand}</span>
        <strong className="operator-device-tile__power">{formatSidebarPower(currentPower)}</strong>
        <span className="operator-device-tile__note">
          {lastReadingAt ? `Ultima lettura ${lastReadingAt}` : "In attesa della prima lettura utile"}
        </span>
      </button>
      <div className="operator-device-tile__actions">
        <button
          className="operator-device-tile__edit"
          type="button"
          onClick={onEdit}
          disabled={deleteBusy}
          title={`Modifica ${device.name}`}
        >
          Modifica
        </button>
        <button
          className="operator-device-tile__delete"
          type="button"
          onClick={onDelete}
          disabled={deleteBusy}
          title={`Rimuovi ${device.name}`}
        >
          {deleteBusy ? "Rimozione..." : "Rimuovi"}
        </button>
      </div>
    </article>
  );
}

function OperatorDeviceGridPanel({
  summary,
  loading,
  error,
  availabilityRatio,
  selectedDeviceId,
  pageDevices,
  totalDevices,
  devicePowerMap,
  deviceOverviewMap,
  settingsActive,
  deleteDeviceBusyId,
  onSelectFleet,
  onSelectDevice,
  onOpenSettingsPage,
  onOpenProvisioning,
  onEditDevice,
  onDeleteDevice,
}: {
  summary: DashboardSummary | null;
  loading: boolean;
  error: string | null;
  availabilityRatio: string;
  selectedDeviceId: string | null;
  pageDevices: Device[];
  totalDevices: number;
  devicePowerMap: DevicePowerMap;
  deviceOverviewMap: DeviceOverviewMap;
  settingsActive: boolean;
  deleteDeviceBusyId: string | null;
  onSelectFleet: () => void;
  onSelectDevice: (deviceId: string) => void;
  onOpenSettingsPage: () => void;
  onOpenProvisioning: () => void;
  onEditDevice: (device: Device) => void;
  onDeleteDevice: (device: Device) => void;
}) {
  const gridVariant =
    pageDevices.length <= 4 ? "operator-device-grid--compact" : "operator-device-grid--standard";

  return (
    <div className="operator-device-board">
      <SidebarBrandMark header />
      <div className="operator-device-board__head">
        <p className="panel-kicker operator-device-board__kicker">Matrice inverter</p>
        <span className="operator-device-board__meta">{totalDevices} inverter</span>
      </div>

      <button
        className={`operator-settings-tile ${
          settingsActive ? "operator-settings-tile--active" : ""
        }`}
        type="button"
        onClick={onOpenSettingsPage}
      >
        <span className="operator-settings-tile__icon">
          <GearIcon />
        </span>
        <span>
          <strong>Impostazioni</strong>
          <small>LAN, COM, health e manutenzione</small>
        </span>
      </button>

      <button className="operator-config-tile" type="button" onClick={onOpenProvisioning}>
        <div className="operator-config-tile__head">
          <strong>Configurazione dispositivi</strong>
          <span className="operator-plant-tile__chip">Setup</span>
        </div>
        <p className="operator-config-tile__note">
          Aggiunta e browsing unificati per seriale, TCP e gateway IP.
        </p>
      </button>

      <button
        className={`operator-plant-tile ${
          selectedDeviceId === null ? "operator-plant-tile--active" : ""
        }`}
        type="button"
        onClick={onSelectFleet}
      >
        <div className="operator-plant-tile__head">
          <strong>Impianto</strong>
          <span className="operator-plant-tile__chip">{availabilityRatio}</span>
        </div>
        <strong className="operator-plant-tile__value">
          {loading
            ? "Caricamento..."
            : error
              ? "--"
              : summary
                ? formatCompactPowerKw(summary.total_power_kw)
                : "--"}
        </strong>
        <p className="operator-plant-tile__note">
          {loading
            ? "Allineamento dispositivi in corso"
            : error
              ? "Stato impianto non disponibile"
              : summary
                ? `${summary.online_devices}/${summary.total_devices} inverter disponibili`
                : "Nessun dispositivo configurato"}
        </p>
      </button>

      {pageDevices.length > 0 ? (
        <div className={`operator-device-grid ${gridVariant}`}>
          {pageDevices.map((device) => (
            <OperatorDeviceTile
              key={device.device_id}
              active={device.device_id === selectedDeviceId}
              device={device}
              overview={deviceOverviewMap[device.device_id] ?? null}
              currentPower={devicePowerMap[device.device_id]}
              deleteBusy={deleteDeviceBusyId === device.device_id}
              onSelect={() => onSelectDevice(device.device_id)}
              onEdit={() => onEditDevice(device)}
              onDelete={() => onDeleteDevice(device)}
            />
          ))}
        </div>
      ) : (
        <div className="operator-device-board__empty">
          {loading
            ? "Caricamento matrice dispositivi..."
            : error
              ? "Matrice dispositivi non disponibile."
              : totalDevices > 0
                ? "Nessun inverter corrisponde ai filtri."
                : "Nessun dispositivo configurato."}
        </div>
      )}
    </div>
  );
}

function OperatorModbusSlaveSettingsCard({
  fleetControl,
  draft,
  busy,
  dirty,
  error,
  message,
  onChange,
  onApply,
  onReset,
}: {
  fleetControl: FleetControlStatus | null;
  draft: ModbusSlaveSettingsDraft | null;
  busy: boolean;
  dirty: boolean;
  error: string | null;
  message: string | null;
  onChange: (
    key: keyof ModbusSlaveSettingsDraft,
    value: string | boolean,
  ) => void;
  onApply: () => void;
  onReset: () => void;
}) {
  const runtimeLabel = fleetControl?.modbus_tcp_slave.running ? "Online" : "Offline";
  const cciLabel = fleetControl?.modbus_tcp_slave.cci_enabled ? "CCI ON" : "CCI OFF";
  const section = SETTINGS_SECTION_CONTENT.cci;

  return (
    <article
      className={`operator-settings-card operator-settings-card--slave ${getSettingsAccentClass(
        "cci",
      )}`}
    >
      <div className="operator-settings-card__header">
        <span className="operator-settings-card__eyebrow">{section.eyebrow}</span>
        <span className="operator-settings-card__icon operator-settings-card__icon--slave">
          <SlaveBridgeIcon />
        </span>
      </div>
      <strong>{section.title}</strong>
      <p className="operator-settings-card__description">{section.description}</p>
      <SettingsGuidanceList items={section.guidance} />

      <div className="operator-settings-card__status-row">
        <span className="wizard-chip">{runtimeLabel}</span>
        <span className="wizard-chip">{cciLabel}</span>
        {dirty ? <span className="wizard-chip wizard-chip--warning">Modifiche non salvate</span> : null}
      </div>

      {draft ? (
        <div className="operator-settings-slave-form">
          <label className="field">
            <span className="field-label">Slave TCP</span>
            <button
              className="secondary-button settings-toggle-button"
              type="button"
              onClick={() => onChange("enabled", !draft.enabled)}
              disabled={busy}
            >
              {draft.enabled ? "ON" : "OFF"}
            </button>
          </label>

          <label className="field">
            <span className="field-label">Host</span>
            <input
              className="field-control"
              type="text"
              value={draft.host}
              onChange={(event) => onChange("host", event.currentTarget.value)}
              disabled={busy}
              placeholder="0.0.0.0"
            />
          </label>

          <label className="field">
            <span className="field-label">Porta slave</span>
            <input
              className="field-control"
              type="number"
              min={1}
              max={65535}
              value={draft.port}
              onChange={(event) => onChange("port", event.currentTarget.value)}
              disabled={busy}
              placeholder="15020"
            />
          </label>

          <label className="field">
            <span className="field-label">ID unita</span>
            <input
              className="field-control"
              type="number"
              min={1}
              max={247}
              value={draft.unitId}
              onChange={(event) => onChange("unitId", event.currentTarget.value)}
              disabled={busy}
              placeholder="1"
            />
          </label>

          <label className="field">
            <span className="field-label">Lettura stabile CCI</span>
            <button
              className="secondary-button settings-toggle-button"
              type="button"
              onClick={() => onChange("cciReadbackEnabled", !draft.cciReadbackEnabled)}
              disabled={busy}
            >
              {draft.cciReadbackEnabled ? "ON" : "OFF"}
            </button>
          </label>

          {draft.cciReadbackEnabled ? (
            <>
              <label className="field">
                <span className="field-label">Range + / - Y (%)</span>
                <input
                  className="field-control"
                  type="number"
                  min={0}
                  max={100}
                  step={0.1}
                  value={draft.cciReadbackRangePercent}
                  onChange={(event) =>
                    onChange("cciReadbackRangePercent", event.currentTarget.value)
                  }
                  disabled={busy}
                  placeholder="1.0"
                />
              </label>

              <label className="field">
                <span className="field-label">Tempo stabilita (s)</span>
                <input
                  className="field-control"
                  type="number"
                  min={0.1}
                  max={3600}
                  step={0.1}
                  value={draft.cciReadbackStableSeconds}
                  onChange={(event) =>
                    onChange("cciReadbackStableSeconds", event.currentTarget.value)
                  }
                  disabled={busy}
                  placeholder="3.0"
                />
              </label>

              <label className="field">
                <span className="field-label">Solo potenza attiva</span>
                <button
                  className="secondary-button settings-toggle-button"
                  type="button"
                  onClick={() =>
                    onChange(
                      "cciReadbackActivePowerOnly",
                      !draft.cciReadbackActivePowerOnly,
                    )
                  }
                  disabled={busy}
                >
                  {draft.cciReadbackActivePowerOnly ? "ON" : "OFF"}
                </button>
              </label>
            </>
          ) : null}
        </div>
      ) : null}

      <div className="operator-settings-card__actions">
        <button className="secondary-button" type="button" onClick={onReset} disabled={!dirty || busy}>
          Ripristina
        </button>
        <button className="action-button" type="button" onClick={onApply} disabled={draft === null || busy}>
          {busy ? "Salvataggio..." : "Salva slave"}
        </button>
      </div>

      {message ? <p className="operator-settings-card__message">{message}</p> : null}
      {error ? <p className="operator-settings-card__message operator-settings-card__message--error">{error}</p> : null}
    </article>
  );
}

function OperatorHsmBridgeSettingsCard({
  fleetControl,
  draft,
  serialPorts,
  busy,
  dirty,
  error,
  message,
  onChange,
  onApply,
  onReset,
}: {
  fleetControl: FleetControlStatus | null;
  draft: HsmBridgeSettingsDraft | null;
  serialPorts: SerialPortInfo[];
  busy: boolean;
  dirty: boolean;
  error: string | null;
  message: string | null;
  onChange: (
    key: keyof HsmBridgeSettingsDraft,
    value: string | boolean,
  ) => void;
  onApply: () => void;
  onReset: () => void;
}) {
  const bridgeStatus = fleetControl?.hsm_bridge.status ?? "offline";
  const bridgeStatusLabel =
    bridgeStatus === "online"
      ? "Bridge attivo"
      : bridgeStatus === "pending"
        ? "Bridge in attesa"
      : "Bridge fermo";
  const portOptions = buildSerialPortChoices(serialPorts, draft?.hsmPort ?? "");
  const inverterPortOptions = buildSerialPortChoices(serialPorts, draft?.inverterPort ?? "");
  const section = SETTINGS_SECTION_CONTENT.hsm;

  return (
    <article
      className={`operator-settings-card operator-settings-card--slave operator-settings-card--bridge ${getSettingsAccentClass(
        "hsm",
      )}`}
    >
      <div className="operator-settings-card__header">
        <span className="operator-settings-card__eyebrow">{section.eyebrow}</span>
        <span className="operator-settings-card__icon operator-settings-card__icon--hsm">
          <HsmBridgeIcon />
        </span>
      </div>
      <strong>{section.title}</strong>
      <p className="operator-settings-card__description">{section.description}</p>
      <SettingsGuidanceList items={section.guidance} />

      <div className="operator-settings-card__status-row">
        <span className="wizard-chip">{bridgeStatusLabel}</span>
        <span className="wizard-chip">{fleetControl?.hsm_bridge.running ? "Runtime ON" : "Runtime OFF"}</span>
        <span className={`wizard-chip ${fleetControl?.hsm_bridge.line_ready ? "" : "wizard-chip--warning"}`}>
          {fleetControl?.hsm_bridge.line_ready ? "Linea pronta" : "Linea da verificare"}
        </span>
        {dirty ? <span className="wizard-chip wizard-chip--warning">Modifiche non salvate</span> : null}
      </div>

      {draft ? (
        <div className="operator-settings-slave-form operator-settings-bridge-form">
          <label className="field">
            <span className="field-label">Bridge HSM</span>
            <button
              className="secondary-button settings-toggle-button"
              type="button"
              onClick={() => onChange("enabled", !draft.enabled)}
              disabled={busy}
            >
              {draft.enabled ? "ON" : "OFF"}
            </button>
          </label>

          <label className="field">
            <span className="field-label">Porta HSM</span>
            <select
              className="field-control"
              value={draft.hsmPort}
              onChange={(event) => onChange("hsmPort", event.currentTarget.value)}
              disabled={busy}
            >
              <option value="">Seleziona porta HSM</option>
              {portOptions.map((option) => (
                <option key={`hsm-${option.value}`} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span className="field-label">Porta inverter</span>
            <select
              className="field-control"
              value={draft.inverterPort}
              onChange={(event) => onChange("inverterPort", event.currentTarget.value)}
              disabled={busy}
            >
              <option value="">Seleziona porta inverter</option>
              {inverterPortOptions.map((option) => (
                <option key={`inv-${option.value}`} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span className="field-label">Baud HSM</span>
            <input
              className="field-control"
              type="number"
              min={1}
              value={draft.hsmBaudRate}
              onChange={(event) => onChange("hsmBaudRate", event.currentTarget.value)}
              disabled={busy}
            />
          </label>

          <label className="field">
            <span className="field-label">Parity HSM</span>
            <select
              className="field-control"
              value={draft.hsmParity}
              onChange={(event) => onChange("hsmParity", event.currentTarget.value)}
              disabled={busy}
            >
              <option value="N">None</option>
              <option value="E">Even</option>
              <option value="O">Odd</option>
            </select>
          </label>

          <label className="field">
            <span className="field-label">Stop bit HSM</span>
            <select
              className="field-control"
              value={draft.hsmStopBits}
              onChange={(event) => onChange("hsmStopBits", event.currentTarget.value)}
              disabled={busy}
            >
              <option value="1">1</option>
              <option value="2">2</option>
            </select>
          </label>

          <label className="field">
            <span className="field-label">Byte size HSM</span>
            <select
              className="field-control"
              value={draft.hsmByteSize}
              onChange={(event) => onChange("hsmByteSize", event.currentTarget.value)}
              disabled={busy}
            >
              <option value="8">8</option>
              <option value="7">7</option>
              <option value="6">6</option>
              <option value="5">5</option>
            </select>
          </label>

          <label className="field">
            <span className="field-label">Frame gap ms</span>
            <input
              className="field-control"
              type="number"
              min={5}
              value={draft.frameGapMs}
              onChange={(event) => onChange("frameGapMs", event.currentTarget.value)}
              disabled={busy}
            />
          </label>

          <label className="field">
            <span className="field-label">Ritardo inoltro ms</span>
            <input
              className="field-control"
              type="number"
              min={0}
              value={draft.forwardDelayMs}
              onChange={(event) => onChange("forwardDelayMs", event.currentTarget.value)}
              disabled={busy}
            />
          </label>

          <label className="field">
            <span className="field-label">Timeout ACK ms</span>
            <input
              className="field-control"
              type="number"
              min={50}
              value={draft.ackTimeoutMs}
              onChange={(event) => onChange("ackTimeoutMs", event.currentTarget.value)}
              disabled={busy}
            />
          </label>
        </div>
      ) : null}

      <div className="operator-settings-card__actions">
        <button className="secondary-button" type="button" onClick={onReset} disabled={!dirty || busy}>
          Ripristina
        </button>
        <button className="action-button" type="button" onClick={onApply} disabled={draft === null || busy}>
          {busy ? "Salvataggio..." : "Salva bridge HSM"}
        </button>
      </div>

      {message ? <p className="operator-settings-card__message">{message}</p> : null}
      {error ? <p className="operator-settings-card__message operator-settings-card__message--error">{error}</p> : null}
    </article>
  );
}

function OperatorSlaveSettingsLaunchCard({
  fleetControl,
  onOpen,
}: {
  fleetControl: FleetControlStatus | null;
  onOpen: () => void;
}) {
  const slaveRuntimeLabel = fleetControl?.modbus_tcp_slave.running ? "Slave online" : "Slave offline";
  const cciLabel = fleetControl?.modbus_tcp_slave.cci_enabled ? "CCI ON" : "CCI OFF";
  const section = SETTINGS_SECTION_CONTENT.cci;

  return (
    <button
      className={`operator-settings-card operator-settings-card--primary operator-settings-card--com ${getSettingsAccentClass(
        "cci",
      )}`}
      type="button"
      onClick={onOpen}
    >
      <div className="operator-settings-card__header">
        <span className="operator-settings-card__eyebrow">{section.eyebrow}</span>
        <span className="operator-settings-card__icon operator-settings-card__icon--slave">
          <SlaveBridgeIcon />
        </span>
      </div>
      <strong>{section.title}</strong>
      <p className="operator-settings-card__description">{section.description}</p>
      <div className="operator-settings-card__status-row">
        <span className="wizard-chip">{slaveRuntimeLabel}</span>
        <span className="wizard-chip">{cciLabel}</span>
      </div>
      <SettingsCardHint section="cci" />
    </button>
  );
}

function OperatorHsmSettingsLaunchCard({
  fleetControl,
  onOpen,
}: {
  fleetControl: FleetControlStatus | null;
  onOpen: () => void;
}) {
  const bridgeStatus = fleetControl?.hsm_bridge.status ?? "offline";
  const bridgeLabel =
    bridgeStatus === "online"
      ? "Bridge attivo"
      : bridgeStatus === "pending"
        ? "Bridge in attesa"
        : "Bridge fermo";
  const lineLabel = fleetControl?.hsm_bridge.line_ready ? "Linea pronta" : "Linea da verificare";
  const section = SETTINGS_SECTION_CONTENT.hsm;

  return (
    <button
      className={`operator-settings-card operator-settings-card--com operator-settings-card--bridge-launch ${getSettingsAccentClass(
        "hsm",
      )}`}
      type="button"
      onClick={onOpen}
    >
      <div className="operator-settings-card__header">
        <span className="operator-settings-card__eyebrow">{section.eyebrow}</span>
        <span className="operator-settings-card__icon operator-settings-card__icon--hsm">
          <HsmBridgeIcon />
        </span>
      </div>
      <strong>{section.title}</strong>
      <p className="operator-settings-card__description">{section.description}</p>
      <div className="operator-settings-card__status-row">
        <span className="wizard-chip">{bridgeLabel}</span>
        <span
          className={`wizard-chip ${
            fleetControl?.hsm_bridge.line_ready ? "wizard-chip--positive" : "wizard-chip--warning"
          }`}
        >
          {lineLabel}
        </span>
      </div>
      <SettingsCardHint section="hsm" />
    </button>
  );
}

function OperatorComSettingsDrawer({
  open,
  fleetControl,
  focusSection,
  onClose,
  onRefreshSerialPorts,
  children,
}: {
  open: boolean;
  fleetControl: FleetControlStatus | null;
  focusSection: OperatorComSettingsSectionKey;
  onClose: () => void;
  onRefreshSerialPorts: () => void;
  children: ReactNode;
}) {
  if (!open) {
    return null;
  }

  const isBridgeSection = focusSection === "bridge";
  const focusedSectionKey: SettingsSectionAccent = isBridgeSection ? "hsm" : "cci";
  const focusedSection = SETTINGS_SECTION_CONTENT[focusedSectionKey];
  const slaveRuntimeLabel = fleetControl?.modbus_tcp_slave.running ? "Online" : "Offline";
  const cciLabel = fleetControl?.modbus_tcp_slave.cci_enabled ? "CCI ON" : "CCI OFF";
  const bridgeStatus = fleetControl?.hsm_bridge.status ?? "offline";
  const bridgeLabel =
    bridgeStatus === "online"
      ? "Attivo"
      : bridgeStatus === "pending"
        ? "In attesa"
        : "Fermo";
  const lineLabel = fleetControl?.hsm_bridge.line_ready ? "Pronta" : "Da verificare";
  const lastAckAt = formatRuntimeTimestamp(fleetControl?.hsm_bridge.last_ack_at ?? null);

  return (
    <div className="settings-backdrop" role="presentation" onClick={onClose}>
      <aside
        aria-labelledby="operator-com-settings-title"
        aria-modal="true"
        className={`settings-drawer operator-com-settings-drawer settings-accent-shell ${getSettingsAccentClass(
          focusedSectionKey,
        )}`}
        role="dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div className="modal-title-group">
            <p className="panel-kicker">{focusedSection.eyebrow}</p>
            <h2 id="operator-com-settings-title">{focusedSection.drawerTitle}</h2>
            <p className="modal-copy">{focusedSection.drawerCopy}</p>
            <div className="settings-accent-pill-row">
              <span className={`settings-accent-pill ${getSettingsAccentClass(focusedSectionKey)}`}>
                {focusedSection.legendLabel}
              </span>
            </div>
          </div>
          <button className="icon-button" type="button" onClick={onClose}>
            Chiudi
          </button>
        </div>

        <div className="settings-content">
          <section className="settings-summary operator-com-settings-summary">
            <p className="panel-kicker">Stato runtime</p>
            <h3>{isBridgeSection ? "Bridge seriale HSM" : "Slave Modbus TCP"}</h3>
            <p className="settings-summary-meta">
              {isBridgeSection
                ? "Il bridge usa la COM HSM e la COM inverter per inoltrare il traffico seriale verso il campo."
                : "Questo canale espone il nostro slave Modbus TCP dedicato al CCI senza influire sulla configurazione HSM."}
            </p>
            <SettingsGuidanceList items={focusedSection.guidance} limit={2} />
            {isBridgeSection ? (
              <>
                <div className="operator-com-settings-meta-grid">
                  <article className="settings-item operator-com-settings-item">
                    <p className="settings-item-label">Bridge HSM</p>
                    <strong className="settings-item-value">{bridgeLabel}</strong>
                  </article>
                  <article className="settings-item operator-com-settings-item">
                    <p className="settings-item-label">Linea inverter</p>
                    <strong className="settings-item-value">{lineLabel}</strong>
                  </article>
                  <article className="settings-item operator-com-settings-item">
                    <p className="settings-item-label">Ultimo ACK</p>
                    <strong className="settings-item-value">{lastAckAt ?? "Nessun ACK"}</strong>
                  </article>
                </div>
                {fleetControl?.hsm_bridge.line_note ? (
                  <p className="operator-com-settings-note">{fleetControl.hsm_bridge.line_note}</p>
                ) : null}
                {fleetControl?.hsm_bridge.last_error ? (
                  <p className="operator-settings-card__message operator-settings-card__message--error">
                    {fleetControl.hsm_bridge.last_error}
                  </p>
                ) : null}
              </>
            ) : (
              <div className="operator-com-settings-meta-grid">
                <article className="settings-item operator-com-settings-item">
                  <p className="settings-item-label">Slave Modbus TCP</p>
                  <strong className="settings-item-value">{slaveRuntimeLabel}</strong>
                </article>
                <article className="settings-item operator-com-settings-item">
                  <p className="settings-item-label">CCI</p>
                  <strong className="settings-item-value">{cciLabel}</strong>
                </article>
                <article className="settings-item operator-com-settings-item">
                  <p className="settings-item-label">Endpoint</p>
                  <strong className="settings-item-value">
                    {fleetControl
                      ? `${fleetControl.modbus_tcp_slave.host}:${fleetControl.modbus_tcp_slave.port}`
                      : "--"}
                  </strong>
                </article>
                <article className="settings-item operator-com-settings-item">
                  <p className="settings-item-label">ID unità</p>
                  <strong className="settings-item-value">
                    {fleetControl?.modbus_tcp_slave.unit_id ?? "--"}
                  </strong>
                </article>
              </div>
            )}
          </section>

          <section className="settings-section">
            <div className="settings-section-header">
              <div>
                <p className="panel-kicker">Configurazione</p>
                <h3 className="detail-section-title">
                  {isBridgeSection ? "Parametri bridge HSM" : "Parametri slave Modbus TCP"}
                </h3>
              </div>
              {isBridgeSection ? (
                <button className="secondary-button" type="button" onClick={onRefreshSerialPorts}>
                  Aggiorna porte
                </button>
              ) : null}
            </div>
            <div className="operator-com-settings-stack">{children}</div>
          </section>
        </div>
      </aside>
    </div>
  );
}

function OperatorHsmBridgeRuntimeGrid({
  fleetControl,
}: {
  fleetControl: FleetControlStatus | null;
}) {
  const bridge = fleetControl?.hsm_bridge;
  if (!bridge) {
    return null;
  }

  const lastAckLabel = formatRuntimeTimestamp(bridge.last_ack_at) ?? "Nessun ACK";
  const lastFrameLabel = formatRuntimeTimestamp(bridge.last_hsm_frame_at) ?? "Nessun frame";
  const rxCardTone =
    bridge.frames_received_count > 0
      ? "operator-com-settings-kpi-card--positive"
      : bridge.enabled
        ? "operator-com-settings-kpi-card--warning"
        : "";
  const forwardedCardTone =
    bridge.frames_forwarded_count > 0
      ? "operator-com-settings-kpi-card--positive"
      : bridge.frames_received_count > 0
        ? "operator-com-settings-kpi-card--warning"
        : "";
  const ackCardTone =
    bridge.ack_ok_count > 0
      ? "operator-com-settings-kpi-card--positive"
      : bridge.running
        ? "operator-com-settings-kpi-card--warning"
        : "";
  const timeoutCardTone =
    bridge.timeout_count > 0
      ? bridge.last_error
        ? "operator-com-settings-kpi-card--error"
        : "operator-com-settings-kpi-card--warning"
      : "";
  const queueCardTone =
    bridge.queue_depth > 0
      ? "operator-com-settings-kpi-card--warning"
      : bridge.running
        ? "operator-com-settings-kpi-card--positive"
        : "";
  const lastAckCardTone =
    bridge.last_ack_at !== null
      ? "operator-com-settings-kpi-card--positive"
      : bridge.last_error
        ? "operator-com-settings-kpi-card--error"
        : bridge.running
          ? "operator-com-settings-kpi-card--warning"
          : "";
  const lineChipTone = bridge.line_ready ? "wizard-chip--positive" : "wizard-chip--warning";

  return (
    <>
      <div className="operator-com-settings-kpi-grid">
        <article className={`operator-com-settings-kpi-card ${rxCardTone}`.trim()}>
          <p className="operator-com-settings-kpi-card__label">Frame RX</p>
          <strong className="operator-com-settings-kpi-card__value">
            {bridge.frames_received_count}
          </strong>
          <span className="operator-com-settings-kpi-card__note">Frame ricevuti da HSM</span>
        </article>
        <article className={`operator-com-settings-kpi-card ${forwardedCardTone}`.trim()}>
          <p className="operator-com-settings-kpi-card__label">Inoltri</p>
          <strong className="operator-com-settings-kpi-card__value">
            {bridge.frames_forwarded_count}
          </strong>
          <span className="operator-com-settings-kpi-card__note">Frame inoltrati agli inverter</span>
        </article>
        <article className={`operator-com-settings-kpi-card ${ackCardTone}`.trim()}>
          <p className="operator-com-settings-kpi-card__label">ACK OK</p>
          <strong className="operator-com-settings-kpi-card__value">{bridge.ack_ok_count}</strong>
          <span className="operator-com-settings-kpi-card__note">Risposte utili dal campo</span>
        </article>
        <article className={`operator-com-settings-kpi-card ${timeoutCardTone}`.trim()}>
          <p className="operator-com-settings-kpi-card__label">Timeout</p>
          <strong className="operator-com-settings-kpi-card__value">{bridge.timeout_count}</strong>
          <span className="operator-com-settings-kpi-card__note">Assenze di ACK inverter</span>
        </article>
        <article className={`operator-com-settings-kpi-card ${queueCardTone}`.trim()}>
          <p className="operator-com-settings-kpi-card__label">Coda bridge</p>
          <strong className="operator-com-settings-kpi-card__value">{bridge.queue_depth}</strong>
          <span className="operator-com-settings-kpi-card__note">Frame ancora in coda</span>
        </article>
        <article className={`operator-com-settings-kpi-card ${lastAckCardTone}`.trim()}>
          <p className="operator-com-settings-kpi-card__label">Ultimo ACK</p>
          <strong className="operator-com-settings-kpi-card__value operator-com-settings-kpi-card__value--small">
            {lastAckLabel}
          </strong>
          <span className="operator-com-settings-kpi-card__note">
            Ultimo frame HSM {lastFrameLabel}
          </span>
        </article>
      </div>
      <div className="operator-com-settings-inline-status">
        <span className={`wizard-chip ${lineChipTone}`.trim()}>
          {bridge.line_ready ? "Linea pronta" : "Linea da verificare"}
        </span>
        <span className="wizard-chip">
          Protocollo {bridge.resolved_protocol ?? "n.d."}
        </span>
        {bridge.resolved_baud_rate ? (
          <span className="wizard-chip">
            {bridge.resolved_baud_rate} baud | {bridge.resolved_parity ?? "N"} |{" "}
            {bridge.resolved_stop_bits ?? 1} stop
          </span>
        ) : null}
      </div>
      {bridge.line_note ? <p className="operator-com-settings-note">{bridge.line_note}</p> : null}
      {bridge.last_error ? (
        <p className="operator-settings-card__message operator-settings-card__message--error">
          {bridge.last_error}
        </p>
      ) : null}
    </>
  );
}

function OperatorComSettingsSection({
  eyebrow,
  title,
  note,
  icon,
  tone = "neutral",
  active = false,
  children,
}: {
  eyebrow: string;
  title: string;
  note: string;
  icon: ReactNode;
  tone?: "neutral" | "accent";
  active?: boolean;
  children: ReactNode;
}) {
  return (
    <section
      className={`operator-com-settings-section ${
        tone === "accent" ? "operator-com-settings-section--accent" : ""
      } ${active ? "operator-com-settings-section--active" : ""}`}
    >
      <div className="operator-com-settings-section__header">
        <div>
          <p className="operator-com-settings-section__eyebrow">{eyebrow}</p>
          <h4 className="operator-com-settings-section__title">{title}</h4>
          <p className="operator-com-settings-section__note">{note}</p>
        </div>
        <span className="operator-com-settings-section__icon">{icon}</span>
      </div>
      {children}
    </section>
  );
}

function OperatorDashboardSettingsCard({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}) {
  const section = SETTINGS_SECTION_CONTENT.dashboard;

  return (
    <article
      className={`operator-settings-card operator-settings-card--dashboard ${getSettingsAccentClass(
        "dashboard",
      )}`}
    >
      <div className="operator-settings-card__header">
        <span className="operator-settings-card__eyebrow">{section.eyebrow}</span>
        <span className="operator-settings-card__icon operator-settings-card__icon--dashboard">
          <SolarBackgroundIcon />
        </span>
      </div>
      <strong>{section.title}</strong>
      <p className="operator-settings-card__description">{section.description}</p>
      <div className="operator-settings-card__status-row">
        <span className={`wizard-chip ${enabled ? "" : "wizard-chip--muted"}`}>
          {enabled ? "Animazione attiva" : "Animazione spenta"}
        </span>
      </div>
      <button
        className="secondary-button settings-toggle-button operator-settings-card__toggle"
        type="button"
        aria-pressed={enabled}
        onClick={() => onToggle(!enabled)}
      >
        <span>{enabled ? "Disabilita" : "Abilita"}</span>
        <strong>{enabled ? "ON" : "OFF"}</strong>
      </button>
      <SettingsCardHint section="dashboard" />
    </article>
  );
}

function OperatorSettingsPage({
  deviceCount,
  systemHealthSummary,
  systemHealthHasAttention,
  fleetControl,
  slaveSettingsDraft,
  slaveSettingsBusy,
  slaveSettingsDirty,
  slaveSettingsError,
  slaveSettingsMessage,
  hsmBridgeSettingsDraft,
  hsmBridgeSettingsBusy,
  hsmBridgeSettingsDirty,
  hsmBridgeSettingsError,
  hsmBridgeSettingsMessage,
  serialPorts,
  deleteAllDevicesBusy,
  solarBackgroundEnabled,
  onOpenProvisioning,
  onOpenComSettings,
  onOpenLanSettings,
  onOpenHealth,
  onOpenControlAudit,
  onOpenHistory,
  onOpenPro,
  onOpenPlant,
  onDeleteAllDevices,
  onSolarBackgroundToggle,
  onSlaveSettingsChange,
  onApplySlaveSettings,
  onResetSlaveSettings,
  onHsmBridgeSettingsChange,
  onApplyHsmBridgeSettings,
  onResetHsmBridgeSettings,
}: {
  deviceCount: number;
  systemHealthSummary: string;
  systemHealthHasAttention: boolean;
  fleetControl: FleetControlStatus | null;
  slaveSettingsDraft: ModbusSlaveSettingsDraft | null;
  slaveSettingsBusy: boolean;
  slaveSettingsDirty: boolean;
  slaveSettingsError: string | null;
  slaveSettingsMessage: string | null;
  hsmBridgeSettingsDraft: HsmBridgeSettingsDraft | null;
  hsmBridgeSettingsBusy: boolean;
  hsmBridgeSettingsDirty: boolean;
  hsmBridgeSettingsError: string | null;
  hsmBridgeSettingsMessage: string | null;
  serialPorts: SerialPortInfo[];
  deleteAllDevicesBusy: boolean;
  solarBackgroundEnabled: boolean;
  onOpenProvisioning: () => void;
  onOpenComSettings: (section: OperatorComSettingsSectionKey) => void;
  onOpenLanSettings: () => void;
  onOpenHealth: () => void;
  onOpenControlAudit: () => void;
  onOpenHistory: () => void;
  onOpenPro: () => void;
  onOpenPlant: () => void;
  onDeleteAllDevices: () => void;
  onSolarBackgroundToggle: (enabled: boolean) => void;
  onSlaveSettingsChange: (
    key: keyof ModbusSlaveSettingsDraft,
    value: string | boolean,
  ) => void;
  onApplySlaveSettings: () => void;
  onResetSlaveSettings: () => void;
  onHsmBridgeSettingsChange: (
    key: keyof HsmBridgeSettingsDraft,
    value: string | boolean,
  ) => void;
  onApplyHsmBridgeSettings: () => void;
  onResetHsmBridgeSettings: () => void;
}) {
  const legendSections: SettingsSectionAccent[] = [
    "cci",
    "hsm",
    "com",
    "lan",
    "health",
    "control",
    "history",
    "dashboard",
  ];

  return (
    <section className="stage-panel operator-settings-page">
      <div className="stage-header operator-settings-page__header">
        <div>
          <p className="panel-kicker">Impostazioni</p>
          <h2>Centro configurazione</h2>
          <p className="stage-copy">
            Accesso unico alle funzioni tecniche: rete, comunicazione, health e manutenzione
            dispositivi.
          </p>
        </div>
        <div className="operator-settings-page__header-actions">
          <button className="secondary-button" type="button" onClick={onOpenPlant}>
            Vista impianto
          </button>
          <span
            className={`operator-settings-page__health ${
              systemHealthHasAttention ? "operator-settings-page__health--attention" : ""
            }`}
          >
            {systemHealthSummary}
          </span>
        </div>
      </div>

      <div className="operator-settings-page__legend" aria-label="Sezioni impostazioni">
        {legendSections.map((sectionKey) => (
          <span
            key={sectionKey}
            className={`settings-accent-pill ${getSettingsAccentClass(sectionKey)}`}
          >
            {SETTINGS_SECTION_CONTENT[sectionKey].legendLabel}
          </span>
        ))}
        <button
          className={`settings-accent-pill operator-settings-visual-pill ${getSettingsAccentClass(
            "dashboard",
          )}`}
          type="button"
          onClick={onOpenPro}
          title="Apri Dashboard Pro"
        >
          <DashboardGridIcon />
          <span>Pro Visual</span>
        </button>
      </div>

      <div className="operator-settings-grid">
        <OperatorSlaveSettingsLaunchCard
          fleetControl={fleetControl}
          onOpen={() => onOpenComSettings("slave")}
        />
        <OperatorHsmSettingsLaunchCard
          fleetControl={fleetControl}
          onOpen={() => onOpenComSettings("bridge")}
        />
        <button
          className={`operator-settings-card operator-settings-card--primary ${getSettingsAccentClass(
            "com",
          )}`}
          type="button"
          onClick={onOpenProvisioning}
        >
          <div className="operator-settings-card__header">
            <span className="operator-settings-card__eyebrow">
              {SETTINGS_SECTION_CONTENT.com.eyebrow}
            </span>
            <span className="operator-settings-card__icon operator-settings-card__icon--primary">
              <ProvisioningIcon />
            </span>
          </div>
          <strong>{SETTINGS_SECTION_CONTENT.com.title}</strong>
          <p className="operator-settings-card__description">
            {SETTINGS_SECTION_CONTENT.com.description}
          </p>
          <SettingsCardHint section="com" />
        </button>
        <button
          className={`operator-settings-card ${getSettingsAccentClass("lan")}`}
          type="button"
          onClick={onOpenLanSettings}
        >
          <div className="operator-settings-card__header">
            <span className="operator-settings-card__eyebrow">
              {SETTINGS_SECTION_CONTENT.lan.eyebrow}
            </span>
            <span className="operator-settings-card__icon operator-settings-card__icon--lan">
              <Rj45Icon />
            </span>
          </div>
          <strong>{SETTINGS_SECTION_CONTENT.lan.title}</strong>
          <p className="operator-settings-card__description">
            {SETTINGS_SECTION_CONTENT.lan.description}
          </p>
          <SettingsCardHint section="lan" />
        </button>
        <button
          className={`operator-settings-card ${getSettingsAccentClass("health")}`}
          type="button"
          onClick={onOpenHealth}
        >
          <div className="operator-settings-card__header">
            <span className="operator-settings-card__eyebrow">
              {SETTINGS_SECTION_CONTENT.health.eyebrow}
            </span>
            <span className="operator-settings-card__icon operator-settings-card__icon--health">
              <HealthPulseIcon />
            </span>
          </div>
          <strong>{SETTINGS_SECTION_CONTENT.health.title}</strong>
          <p className="operator-settings-card__description">
            {SETTINGS_SECTION_CONTENT.health.description}
          </p>
          <SettingsCardHint section="health" />
        </button>
        <button
          className={`operator-settings-card operator-settings-card--control ${getSettingsAccentClass(
            "control",
          )}`}
          type="button"
          onClick={onOpenControlAudit}
        >
          <div className="operator-settings-card__header">
            <span className="operator-settings-card__eyebrow">
              {SETTINGS_SECTION_CONTENT.control.eyebrow}
            </span>
            <span className="operator-settings-card__icon operator-settings-card__icon--control">
              <ControlAuditIcon />
            </span>
          </div>
          <strong>{SETTINGS_SECTION_CONTENT.control.title}</strong>
          <p className="operator-settings-card__description">
            {SETTINGS_SECTION_CONTENT.control.description}
          </p>
          <SettingsCardHint section="control" />
        </button>
        <button
          className={`operator-settings-card ${getSettingsAccentClass("history")}`}
          type="button"
          onClick={onOpenHistory}
        >
          <div className="operator-settings-card__header">
            <span className="operator-settings-card__eyebrow">
              {SETTINGS_SECTION_CONTENT.history.eyebrow}
            </span>
            <span className="operator-settings-card__icon operator-settings-card__icon--history">
              <HistoryChartIcon />
            </span>
          </div>
          <strong>{SETTINGS_SECTION_CONTENT.history.title}</strong>
          <p className="operator-settings-card__description">
            {SETTINGS_SECTION_CONTENT.history.description}
          </p>
          <SettingsCardHint section="history" />
        </button>
        <OperatorDashboardSettingsCard
          enabled={solarBackgroundEnabled}
          onToggle={onSolarBackgroundToggle}
        />
      </div>

      <article className="operator-settings-danger">
        <div>
          <p className="panel-kicker">Manutenzione dispositivi</p>
          <strong>{deviceCount} dispositivi configurati</strong>
          <span>
            La rimozione completa e disponibile qui; la rimozione singola e disponibile su ogni
            card inverter nella sidebar.
          </span>
        </div>
        <button
          className="danger-outline-button"
          type="button"
          onClick={onDeleteAllDevices}
          disabled={deviceCount === 0 || deleteAllDevicesBusy}
        >
          {deleteAllDevicesBusy ? "Rimozione..." : "Rimuovi tutti"}
        </button>
      </article>
    </section>
  );
}

function OperatorControlAuditPage({
  fleetControl,
  health,
  loading,
  error,
  onBackToSettings,
  onOpenPlant,
  onOpenHealth,
  onOpenHistory,
}: {
  fleetControl: FleetControlStatus | null;
  health: SystemHealthResponse | null;
  loading: boolean;
  error: string | null;
  onBackToSettings: () => void;
  onOpenPlant: () => void;
  onOpenHealth: () => void;
  onOpenHistory: () => void;
}) {
  const section = SETTINGS_SECTION_CONTENT.control;

  return (
    <section className={`operator-control-audit-page ${getSettingsAccentClass("control")}`}>
      <div className="stage-panel operator-control-audit-page__header settings-accent-shell">
        <div className="stage-header operator-control-audit-page__top">
          <div>
            <p className="panel-kicker">{section.eyebrow}</p>
            <h2>{section.title}</h2>
            <p className="stage-copy">{section.drawerCopy}</p>
          </div>
          <div className="stage-header-actions">
            <button className="secondary-button" type="button" onClick={onBackToSettings}>
              Impostazioni
            </button>
            <button className="secondary-button" type="button" onClick={onOpenPlant}>
              Vista impianto
            </button>
          </div>
        </div>
        <SettingsGuidanceList items={section.guidance} />
      </div>

      <div className="operator-control-audit-page__grid">
        <OperatorPlantCommandabilityPanel
          fleetControl={fleetControl}
          health={health}
          loading={loading}
          error={error}
          onOpenHealth={onOpenHealth}
        />
        <OperatorBroadcastTopologyPanel health={health} onOpenHealth={onOpenHealth} />
        <OperatorCommandAuditPanel fleetControl={fleetControl} onOpenHistory={onOpenHistory} />
        <OperatorControlConfidencePanel fleetControl={fleetControl} />
      </div>
    </section>
  );
}

function FleetSetpointPanel({
  loading,
  fleetSetpointValue,
  fleetSetpointNote,
  fleetSetpointConfigLabel,
  fleetSetpointCaption,
  inputValue,
  actionBusy,
  actionError,
  onInputChange,
  onApply,
  onClear,
}: {
  loading: boolean;
  fleetSetpointValue: string;
  fleetSetpointNote: string;
  fleetSetpointConfigLabel: string;
  fleetSetpointCaption: string;
  inputValue: string;
  actionBusy: boolean;
  actionError: string | null;
  onInputChange: (value: string) => void;
  onApply: () => void;
  onClear: () => void;
}) {
  return (
    <section className="stage-panel fleet-setpoint-panel">
      <div className="stage-header">
        <div>
          <p className="panel-kicker">Controllo flotta</p>
          <h2>Setpoint potenza attiva</h2>
        </div>
        <span className="stage-meta">Target attivo e comando manuale dell’impianto</span>
      </div>

      <div className="fleet-setpoint-panel__grid">
        <article className="fleet-setpoint-panel__status">
          <span>Setpoint attivo</span>
          <strong>{loading ? "Caricamento..." : fleetSetpointValue}</strong>
          <p>{fleetSetpointNote}</p>
          <p>{fleetSetpointConfigLabel}</p>
          <p>{fleetSetpointCaption}</p>
        </article>

        <article className="fleet-setpoint-panel__editor">
          <label className="field">
            <span className="field-label">Nuovo setpoint %</span>
            <input
              className="field-control"
              type="number"
              min={0}
              max={100}
              step={1}
              value={inputValue}
              onChange={(event) => {
                const nextValue = event.currentTarget.value;
                onInputChange(nextValue);
              }}
              disabled={actionBusy}
              placeholder="0-100"
            />
          </label>
          <p className="confirm-note">
            Scrittura manuale via API. Se arriva un target esterno con priorita superiore verra
            mantenuto quello dominante.
          </p>
          {actionError ? (
            <div className="panel-state panel-state--error">{actionError}</div>
          ) : null}
          <div className="fleet-setpoint-panel__actions">
            <button
              className="secondary-button"
              type="button"
              onClick={onClear}
              disabled={actionBusy}
            >
              {actionBusy ? "Attendi..." : "Azzera"}
            </button>
            <button
              className="action-button"
              type="button"
              onClick={onApply}
              disabled={actionBusy}
            >
              {actionBusy ? "Applicazione..." : "Applica setpoint"}
            </button>
          </div>
        </article>
      </div>
    </section>
  );
}

function CompactDeviceSetpointControl({
  inputValue,
  lastSetpointDisplay,
  lastSetpointAt,
  actionBusy,
  actionError,
  actionMessage,
  onInputChange,
  onApply,
}: {
  inputValue: string;
  lastSetpointDisplay: string | null;
  lastSetpointAt: string | null;
  actionBusy: boolean;
  actionError: string | null;
  actionMessage: string | null;
  onInputChange: (value: string) => void;
  onApply: () => void;
}) {
  const lastSetpointTimestamp = formatStoredSetpointTimestamp(lastSetpointAt);
  return (
    <div className="device-setpoint-inline">
      <span className="device-setpoint-inline__eyebrow">Setpoint inverter %</span>
      <p className="device-setpoint-inline__saved">
        {lastSetpointDisplay ? (
          <>
            <strong>{lastSetpointDisplay}</strong>
            <span>
              {lastSetpointTimestamp
                ? `Ultimo target noto del ${lastSetpointTimestamp}`
                : "Ultimo target noto"}
            </span>
          </>
        ) : (
          <span>Nessun target salvato.</span>
        )}
      </p>
      <div className="device-setpoint-inline__controls">
        <input
          className="field-control device-setpoint-inline__input"
          type="number"
          min={0}
          max={100}
          step={1}
          value={inputValue}
          onChange={(event) => {
            const nextValue = event.currentTarget.value;
            onInputChange(nextValue);
          }}
          disabled={actionBusy}
          placeholder="0-100"
          aria-label="Setpoint inverter percentuale"
        />
        <button
          className="secondary-button"
          type="button"
          onClick={onApply}
          disabled={actionBusy}
        >
          {actionBusy ? "Invio..." : "Applica"}
        </button>
      </div>
      {actionError ? (
        <p className="device-setpoint-inline__feedback device-setpoint-inline__feedback--error">
          {actionError}
        </p>
      ) : actionMessage ? (
        <p className="device-setpoint-inline__feedback">{actionMessage}</p>
      ) : null}
    </div>
  );
}

function getDisplayValue(value: string, loading: boolean, hasError: boolean): string {
  if (loading) {
    return "Caricamento...";
  }

  if (hasError) {
    return "--";
  }

  return value;
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

function getStatusTone(status: string): SummaryTone {
  switch (status.toLowerCase()) {
    case "online":
      return "positive";
    case "degraded":
    case "offline":
    case "fault":
      return "warning";
    default:
      return "neutral";
  }
}

function getStatusPriority(status: string): number {
  switch (status.toLowerCase()) {
    case "online":
      return 4;
    case "degraded":
      return 3;
    case "pending":
      return 2;
    case "warning":
      return 1;
    default:
      return 0;
  }
}

function normalizeOperatorDeviceSearch(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function getOperatorStatusSortPriority(status: string): number {
  switch (status.toLowerCase()) {
    case "fault":
      return 0;
    case "offline":
      return 1;
    case "pending":
      return 2;
    case "degraded":
      return 3;
    case "warning":
      return 4;
    case "online":
      return 5;
    default:
      return 6;
  }
}

function filterAndSortOperatorDevices(
  devices: Device[],
  powerMap: DevicePowerMap,
  searchTerm: string,
  statusFilter: OperatorDeviceStatusFilter,
  sortMode: OperatorDeviceSortMode,
): Device[] {
  const normalizedSearch = normalizeOperatorDeviceSearch(searchTerm);
  return devices
    .filter((device) => {
      if (statusFilter !== "all" && device.status.toLowerCase() !== statusFilter) {
        return false;
      }

      if (!normalizedSearch) {
        return true;
      }

      const searchable = normalizeOperatorDeviceSearch(
        `${device.name} ${device.brand} ${device.model} ${device.protocol} ${device.transport}`,
      );
      return searchable.includes(normalizedSearch);
    })
    .sort((left, right) => {
      if (sortMode === "name") {
        return left.name.localeCompare(right.name, "it", { numeric: true });
      }

      const leftPower = powerMap[left.device_id] ?? Number.NEGATIVE_INFINITY;
      const rightPower = powerMap[right.device_id] ?? Number.NEGATIVE_INFINITY;
      if (sortMode === "power_desc") {
        const powerDelta = rightPower - leftPower;
        return powerDelta !== 0 ? powerDelta : left.name.localeCompare(right.name, "it", { numeric: true });
      }
      if (sortMode === "power_asc") {
        const powerDelta = leftPower - rightPower;
        return powerDelta !== 0 ? powerDelta : left.name.localeCompare(right.name, "it", { numeric: true });
      }

      const statusDelta =
        getOperatorStatusSortPriority(left.status) - getOperatorStatusSortPriority(right.status);
      if (statusDelta !== 0) {
        return statusDelta;
      }

      return left.name.localeCompare(right.name, "it", { numeric: true });
    });
}

function getReferenceDevice(
  devices: Device[],
  overviewMap: DeviceOverviewMap,
  powerMap: DevicePowerMap,
): ReferenceDeviceContext | null {
  return (
    devices
      .map((device) => ({
        device,
        overview: overviewMap[device.device_id] ?? null,
        power: powerMap[device.device_id] ?? Number.NEGATIVE_INFINITY,
      }))
      .filter(
        (
          candidate,
        ): candidate is { device: Device; overview: DeviceOverview; power: number } =>
          candidate.overview !== null,
      )
      .sort((left, right) => {
        const statusDelta =
          getStatusPriority(right.device.status) - getStatusPriority(left.device.status);
        if (statusDelta !== 0) {
          return statusDelta;
        }

        return (right.power ?? Number.NEGATIVE_INFINITY) - (left.power ?? Number.NEGATIVE_INFINITY);
      })
      .map(({ device, overview }) => ({ device, overview }))[0] ?? null
  );
}

function buildSummaryItems(
  summary: DashboardSummary | null,
  loading: boolean,
  hasError: boolean,
): SummaryItem[] {
  return [
    {
      label: "Dispositivi totali",
      value: getDisplayValue(
        summary ? integerFormatter.format(summary.total_devices) : "--",
        loading,
        hasError,
      ),
      caption: "Dispositivi configurati nel parco inverter",
      tone: "neutral",
    },
    {
      label: "Dispositivi online",
      value: getDisplayValue(
        summary ? integerFormatter.format(summary.online_devices) : "--",
        loading,
        hasError,
      ),
      caption: "Telemetria attiva in arrivo",
      tone: "positive",
    },
    {
      label: "Dispositivi offline",
      value: getDisplayValue(
        summary ? integerFormatter.format(summary.offline_devices) : "--",
        loading,
        hasError,
      ),
      caption: "In attesa di comunicazione",
      tone: "neutral",
    },
    {
      label: "Allarmi attivi",
      value: getDisplayValue(
        summary ? integerFormatter.format(summary.active_alarms) : "--",
        loading,
        hasError,
      ),
      caption: "Richiedono verifica operatore",
      tone: "warning",
    },
    {
      label: "Potenza totale",
      value: getDisplayValue(
        summary ? `${metricFormatter.format(summary.total_power_kw)} kW` : "--",
        loading,
        hasError,
      ),
      caption: "Produzione istantanea dell'impianto",
      tone: "positive",
    },
    {
      label: "Energia giornaliera",
      value: getDisplayValue(
        summary ? `${metricFormatter.format(summary.daily_energy_kwh)} kWh` : "--",
        loading,
        hasError,
      ),
      caption: "Accumulo dalle 00:00",
      tone: "neutral",
    },
    {
      label: "Energia totale",
      value: getDisplayValue(
        summary ? `${metricFormatter.format(summary.total_energy_kwh)} kWh` : "--",
        loading,
        hasError,
      ),
      caption: "Produzione complessiva dell'impianto",
      tone: "neutral",
    },
  ];
}

function SummaryCard({ label, value, caption, tone }: SummaryItem) {
  return (
    <article className={`summary-card summary-card--${tone}`}>
      <p className="summary-label">{label}</p>
      <strong className="summary-value">{value}</strong>
      <p className="summary-caption">{caption}</p>
    </article>
  );
}

function FleetSetpointSummaryCard({
  loading,
  fleetControl,
  fleetSetpointValue,
  fleetSetpointNote,
  fleetSetpointConfigLabel,
  fleetSetpointCaption,
  cciToggleBusy,
  cciToggleError,
  onToggleCci,
}: {
  loading: boolean;
  fleetControl: FleetControlStatus | null;
  fleetSetpointValue: string;
  fleetSetpointNote: string;
  fleetSetpointConfigLabel: string;
  fleetSetpointCaption: string;
  cciToggleBusy: boolean;
  cciToggleError: string | null;
  onToggleCci: () => void;
}) {
  return (
    <article className="summary-card summary-card--command">
      <p className="summary-label">Setpoint esterno</p>
      <div className="summary-card-setpoint">
        <strong className="summary-card-setpoint__value">
          {loading ? "Caricamento..." : fleetSetpointValue}
        </strong>
        <CciConnectionIndicator fleetControl={fleetControl} />
        <CciControlToggle
          fleetControl={fleetControl}
          busy={cciToggleBusy}
          error={cciToggleError}
          onToggle={onToggleCci}
        />
        <span>{fleetSetpointNote}</span>
        <span>{fleetSetpointConfigLabel}</span>
        <span>{fleetSetpointCaption}</span>
      </div>
    </article>
  );
}

function PlantPowerControlCard({
  label,
  loading,
  value,
  caption,
  inputValue,
  actionBusy,
  actionError,
  onInputChange,
  onApply,
  onClear,
}: {
  label: string;
  loading: boolean;
  value: string;
  caption: string;
  inputValue: string;
  actionBusy: boolean;
  actionError: string | null;
  onInputChange: (value: string) => void;
  onApply: () => void;
  onClear: () => void;
}) {
  return (
    <div className="lite-hero-panel__summary plant-hero-summary">
      <span>{label}</span>
      <strong>{loading ? "Caricamento..." : value}</strong>
      <p>{caption}</p>
      <div className="summary-card-inline-setpoint summary-card-inline-setpoint--hero">
        <div className="summary-card-inline-setpoint__head">
          <span className="summary-card-inline-setpoint__label">Setpoint manuale</span>
          <div className="summary-card-inline-setpoint__controls">
            <input
              className="field-control summary-card-inline-setpoint__input"
              type="number"
              min={0}
              max={100}
              step={1}
              value={inputValue}
              onChange={(event) => {
                const nextValue = event.currentTarget.value;
                onInputChange(nextValue);
              }}
              disabled={actionBusy}
              placeholder="0-100"
              aria-label="Setpoint impianto percentuale"
            />
            <button
              className="secondary-button"
              type="button"
              onClick={onClear}
              disabled={actionBusy}
            >
              {actionBusy ? "Attendi..." : "Azzera"}
            </button>
            <button
              className="action-button"
              type="button"
              onClick={onApply}
              disabled={actionBusy}
            >
              {actionBusy ? "Applicazione..." : "Applica"}
            </button>
          </div>
        </div>
        {actionError ? (
          <p className="summary-card-inline-setpoint__feedback summary-card-inline-setpoint__feedback--error">
            {actionError}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function formatFleetSetpointValue(fleetControl: FleetControlStatus | null): string {
  if (fleetControl?.active_power_limit_percent == null) {
    return "Non impostato";
  }

  return `${metricFormatter.format(fleetControl.active_power_limit_percent)} %`;
}

function translateFleetSourceLabel(source: string | null | undefined): string {
  if (source === "modbus_tcp_slave") {
    return "Slave Modbus TCP";
  }
  if (source === "api") {
    return "API";
  }
  if (!source) {
    return "Nessuna sorgente";
  }
  return source;
}

function buildFleetSetpointNote(fleetControl: FleetControlStatus | null): string {
  if (fleetControl === null) {
    return "Slave Modbus TCP non disponibile.";
  }

  if (fleetControl.active_power_limit_percent == null) {
    if (fleetControl.device_summary.total_devices === 0) {
      return "Nessun device configurato per il controllo flotta.";
    }

    const compatibilityLabel =
      fleetControl.device_summary.ineligible_devices > 0
        ? `${fleetControl.device_summary.eligible_devices} compatibili | ${fleetControl.device_summary.ineligible_devices} non supportati`
        : `${fleetControl.device_summary.eligible_devices} device compatibili al target globale`;

    return fleetControl.modbus_tcp_slave.running
      ? `Nessun target attivo. ${compatibilityLabel}.`
      : `Slave Modbus TCP non attivo. ${compatibilityLabel}.`;
  }

  const summary = fleetControl.device_summary;
  if (summary.eligible_devices <= 0) {
    return "Target presente, ma nessun device supporta il controllo potenza globale.";
  }

  const statusParts = [`Inviati ${summary.aligned_devices}/${summary.eligible_devices}`];
  if (summary.pending_devices > 0) {
    statusParts.push(`${summary.pending_devices} in invio`);
  }
  if (summary.error_devices > 0) {
    statusParts.push(`${summary.error_devices} con errore`);
  }
  const blockedCount = summary.blocked_devices + summary.ineligible_devices;
  if (blockedCount > 0) {
    statusParts.push(`${blockedCount} bloccati`);
  }
  return statusParts.join(" | ");
}

function buildFleetSetpointConfigLabel(fleetControl: FleetControlStatus | null): string {
  if (fleetControl === null) {
    return "Config slave non disponibile";
  }

  const config = fleetControl.modbus_tcp_slave;
  const sourceLabel = translateFleetSourceLabel(fleetControl.updated_source);
  return `${sourceLabel} | CCI ${config.cci_enabled ? "ON" : "OFF"} | ${config.enabled ? "Slave TCP" : "Slave TCP off"} ${config.host}:${config.port} | ID ${config.unit_id}`;
}

function buildFleetSetpointCaption(fleetControl: FleetControlStatus | null): string {
  if (fleetControl === null) {
    return "Controllo flotta non disponibile.";
  }

  if (fleetControl.source_policy.last_rejected_reason) {
    const rejectedSource = translateFleetSourceLabel(
      fleetControl.source_policy.last_rejected_source,
    );
    return `Ultimo override ignorato da ${rejectedSource}: priorita inferiore rispetto alla sorgente attiva.`;
  }

  if (fleetControl.updated_at == null) {
    return "Controllo flotta pronto a ricevere un target globale.";
  }

  const updatedAt = new Date(fleetControl.updated_at);
  if (Number.isNaN(updatedAt.getTime())) {
    return "Controllo flotta con target attivo.";
  }

  return `Ultimo target ${dateTimeFormatter.format(updatedAt)}`;
}

function translateCciConnectionStatus(status: "online" | "pending" | "offline"): string {
  switch (status) {
    case "online":
      return "CCI online";
    case "pending":
      return "CCI in attesa";
    case "offline":
      return "CCI offline";
    default:
      return "CCI";
  }
}

function buildCciConnectionCaption(fleetControl: FleetControlStatus | null): string {
  if (fleetControl === null) {
    return "Slave Modbus TCP non disponibile.";
  }

  const connection = fleetControl.modbus_tcp_slave.cci_connection;
  if (connection.status === "online") {
    const activityAt = formatRuntimeTimestamp(connection.last_activity_at);
    if (activityAt) {
      return `Ultima attivita ${activityAt}`;
    }

    const connectedAt = formatRuntimeTimestamp(connection.last_connected_at);
    return connectedAt ? `Connesso dal ${connectedAt}` : "Connessione CCI attiva";
  }

  if (connection.status === "pending") {
    return "In attesa della prima connessione al nostro slave Modbus TCP";
  }

  const disconnectedAt = formatRuntimeTimestamp(connection.last_disconnected_at);
  return disconnectedAt ? `Ultimo distacco ${disconnectedAt}` : "Nessuna connessione CCI attiva";
}

function CciConnectionIndicator({
  fleetControl,
}: {
  fleetControl: FleetControlStatus | null;
}) {
  const status = fleetControl?.modbus_tcp_slave.cci_connection.status ?? "offline";
  const label = translateCciConnectionStatus(status);
  const caption = buildCciConnectionCaption(fleetControl);

  return (
    <div className={`cci-indicator cci-indicator--${status}`}>
      <span className="cci-indicator__led" aria-hidden="true" />
      <div className="cci-indicator__copy">
        <strong>{label}</strong>
        <span>{caption}</span>
      </div>
    </div>
  );
}

function CciControlToggle({
  fleetControl,
  busy,
  error,
  onToggle,
}: {
  fleetControl: FleetControlStatus | null;
  busy: boolean;
  error: string | null;
  onToggle: () => void;
}) {
  const cciEnabled = fleetControl?.modbus_tcp_slave.cci_enabled ?? false;

  return (
    <>
      <span className="summary-card-setpoint__toggle-row">
        <span className="summary-card-setpoint__toggle-label">CCI</span>
        <button
          className={`summary-card-setpoint__toggle ${
            cciEnabled ? "summary-card-setpoint__toggle--on" : "summary-card-setpoint__toggle--off"
          }`}
          type="button"
          onClick={onToggle}
          disabled={fleetControl === null || busy}
        >
          {busy ? "Attendi..." : cciEnabled ? "ON" : "OFF"}
        </button>
      </span>
      {error ? <span className="summary-card-setpoint__error">{error}</span> : null}
    </>
  );
}

function buildSelectedSummaryItems(
  device: Device,
  overview: DeviceOverview | null,
): SummaryItem[] {
  return [
    {
      label: "Stato dispositivo",
      value: translateStatusLabel(device.status),
      caption: "Esito ultimo ciclo di comunicazione",
      tone: getStatusTone(device.status),
    },
    {
      label: "Tempo di risposta",
      value: overview ? `${overview.diagnostics.response_time_ms} ms` : "--",
      caption: "Ultimo polling completato",
      tone: "neutral",
    },
    {
      label: "Tentativi",
      value: overview ? String(overview.diagnostics.retries) : "--",
      caption: "Recovery configurato per il driver",
      tone: "neutral",
    },
    {
      label: "Comandi esposti",
      value: overview ? integerFormatter.format(overview.commands.length) : "--",
      caption: "Setpoint numerici disponibili sul modello",
      tone: "positive",
    },
  ];
}

function countHealthRuntimeIssues(health: SystemHealthResponse | null): number {
  if (health === null) {
    return 0;
  }

  const runtimeIssues = health.endpoint_runtimes.filter(
    (runtime) => runtime.state === "degraded" || runtime.state === "cooldown",
  ).length;
  const broadcastIssues = (health.broadcast_groups ?? []).filter(
    (group) => group.state === "blocked" || group.state === "warning",
  ).length;
  return runtimeIssues + broadcastIssues;
}

function buildSystemHealthSummary(
  health: SystemHealthResponse | null,
  loading: boolean,
  error: string | null,
): string {
  if (loading) {
    return "Caricamento stato sistema...";
  }

  if (error !== null || health === null) {
    return "Health non disponibile";
  }

  if (health.status_counts.total === 0) {
    return health.polling.running ? "Nessun dispositivo configurato" : "Polling fermo";
  }

  const attentionItems: string[] = [];
  const alertCount = health.status_counts.warning + health.status_counts.fault;
  const runtimeIssues = countHealthRuntimeIssues(health);

  if (!health.polling.running) {
    attentionItems.push("polling fermo");
  }
  if (health.modbus_tcp_slave.startup_error !== null) {
    attentionItems.push("slave Modbus TCP da verificare");
  }
  if (health.status_counts.offline > 0) {
    attentionItems.push(`${health.status_counts.offline} offline`);
  }
  if (alertCount > 0) {
    attentionItems.push(`${alertCount} con allarmi`);
  }
  if (runtimeIssues > 0) {
    attentionItems.push(`${runtimeIssues} endpoint/broadcast da verificare`);
  }

  if (attentionItems.length === 0) {
    return health.status_counts.pending > 0
      ? `Stabile | ${health.status_counts.online}/${health.status_counts.total} online, ${health.status_counts.pending} in attesa`
      : `Stabile | ${health.status_counts.online}/${health.status_counts.total} online`;
  }

  return `Richiede attenzione | ${attentionItems.join(" | ")}`;
}

function buildBroadcastPlanSummary(health: SystemHealthResponse | null): {
  totalGroups: number;
  readyGroups: number;
  warningGroups: number;
  blockedGroups: number;
  readyDevices: number;
  totalDevices: number;
} {
  const groups = health?.broadcast_groups ?? [];
  return groups.reduce(
    (summary, group) => {
      summary.totalGroups += 1;
      summary.totalDevices += group.device_count;
      if (group.state === "ready") {
        summary.readyGroups += 1;
        summary.readyDevices += group.device_count;
      } else if (group.state === "warning") {
        summary.warningGroups += 1;
      } else if (group.state === "blocked") {
        summary.blockedGroups += 1;
      }
      return summary;
    },
    {
      totalGroups: 0,
      readyGroups: 0,
      warningGroups: 0,
      blockedGroups: 0,
      readyDevices: 0,
      totalDevices: 0,
    },
  );
}

function buildOperatorCommandabilitySnapshot(
  fleetControl: FleetControlStatus | null,
  health: SystemHealthResponse | null,
  loading: boolean,
  error: string | null,
): OperatorCommandabilitySnapshot {
  const broadcast = buildBroadcastPlanSummary(health);

  if ((loading && fleetControl === null) || fleetControl === null) {
    return {
      state: "idle",
      answer: "In lettura",
      headline: "Stato comando in sincronizzazione",
      detail:
        error ?? "Il backend sta aggiornando lo stato flotta prima di dichiarare il comando impianto.",
      metrics: [
        {
          label: "Compatibili",
          value: "--",
          note: "In attesa stato flotta",
          tone: "neutral",
        },
        {
          label: "Broadcast",
          value: "--",
          note: "In attesa topologia",
          tone: "neutral",
        },
        {
          label: "Ultimo dispatch",
          value: "Mai",
          note: "Nessun comando locale letto",
          tone: "neutral",
        },
      ],
      issues: error ? [error] : [],
    };
  }

  const summary = fleetControl.device_summary;
  const readinessState = fleetControl.readiness.overall_state;
  const hardIssues: string[] = [];
  const softIssues: string[] = [];

  if (summary.total_devices <= 0) {
    hardIssues.push("Nessun device configurato per il controllo flotta.");
  }
  if (summary.total_devices > 0 && summary.eligible_devices <= 0) {
    hardIssues.push("Nessun device espone un comando compatibile per il target globale.");
  }
  if (health !== null && !health.polling.running) {
    hardIssues.push("Polling fermo: il runtime non sta aggiornando i device.");
  }
  if (health?.modbus_tcp_slave.startup_error) {
    hardIssues.push("Slave Modbus TCP CCI con errore di avvio.");
  }
  if (readinessState === "fail") {
    hardIssues.push("Readiness con verifiche bloccanti aperte.");
  }
  if (broadcast.blockedGroups > 0) {
    hardIssues.push(`${broadcast.blockedGroups} endpoint non possono usare il broadcast.`);
  }

  if (readinessState === "warn") {
    softIssues.push("Readiness con verifiche da completare.");
  }
  if (summary.pending_devices > 0) {
    softIssues.push(`${summary.pending_devices} device ancora in invio.`);
  }
  if (summary.error_devices > 0) {
    softIssues.push(`${summary.error_devices} device in errore sull'ultimo dispatch.`);
  }
  if (broadcast.warningGroups > 0) {
    softIssues.push(`${broadcast.warningGroups} endpoint broadcast da verificare.`);
  }
  if (health !== null && health.status_counts.offline > 0) {
    softIssues.push(`${health.status_counts.offline} device offline.`);
  }
  if (error) {
    softIssues.push(error);
  }

  const state: OperatorCommandabilityState =
    hardIssues.length > 0 ? "blocked" : softIssues.length > 0 ? "warning" : "ready";
  const targetLabel = formatPercentValue(fleetControl.active_power_limit_percent);
  const dispatchAt = formatRuntimeTimestamp(fleetControl.last_dispatch_at);
  const broadcastValue =
    broadcast.totalGroups > 0
      ? `${broadcast.readyGroups}/${broadcast.totalGroups}`
      : "Per-device";
  const broadcastNote =
    broadcast.totalGroups > 0
      ? `${broadcast.readyDevices}/${broadcast.totalDevices} device coperti da broadcast pronto`
      : "Nessun endpoint condiviso: invio singolo per device";

  return {
    state,
    answer:
      state === "ready" ? "Si" : state === "warning" ? "Si, con avvisi" : "No",
    headline:
      state === "ready"
        ? "Pronto per il prossimo target"
        : state === "warning"
          ? "Comando possibile, ma da sorvegliare"
          : "Comando bloccato finche non si risolvono le verifiche",
    detail:
      hardIssues[0] ??
      softIssues[0] ??
      "Endpoint, readiness e profili comando sono coerenti con l'invio flotta.",
    metrics: [
      {
        label: "Compatibili",
        value: `${summary.eligible_devices}/${summary.total_devices}`,
        note: `${summary.ineligible_devices} non supportati dal target globale`,
        tone: summary.eligible_devices > 0 ? "positive" : "warning",
      },
      {
        label: "Broadcast",
        value: broadcastValue,
        note: broadcastNote,
        tone: broadcast.blockedGroups > 0 || broadcast.warningGroups > 0 ? "warning" : "positive",
      },
      {
        label: "Ultimo dispatch",
        value: dispatchAt ?? "Mai",
        note: `${fleetControl.last_dispatch_ok_count} ok | ${fleetControl.last_dispatch_error_count} errori | ${fleetControl.last_dispatch_skipped_count} saltati`,
        tone: fleetControl.last_dispatch_error_count > 0 ? "warning" : "neutral",
      },
      {
        label: "Target attivo",
        value: targetLabel,
        note: `Sorgente ${translateFleetSourceLabel(fleetControl.updated_source)}`,
        tone: fleetControl.active_power_limit_percent == null ? "neutral" : "positive",
      },
    ],
    issues: [...hardIssues, ...softIssues].slice(0, 4),
  };
}

function getDispatchDiagnosticText(
  diagnostics: Record<string, string | number | boolean>,
  key: string,
): string | null {
  const value = diagnostics[key];
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function buildDispatchEndpointLabel(
  result: FleetControlStatus["last_device_results"][number],
): string {
  const broadcastEndpoint = getDispatchDiagnosticText(result.diagnostics, "broadcast_endpoint");
  if (broadcastEndpoint) {
    return broadcastEndpoint;
  }

  const endpoint = getDispatchDiagnosticText(result.diagnostics, "endpoint");
  if (endpoint) {
    return endpoint;
  }

  return `${result.protocol} | ${result.transport}`;
}

function translateDispatchOutcome(
  outcome: FleetControlStatus["last_device_results"][number]["outcome"],
): string {
  switch (outcome) {
    case "ok":
      return "OK";
    case "pending":
      return "In invio";
    case "blocked":
      return "Bloccato";
    case "error":
      return "Errore";
    default:
      return outcome;
  }
}

function formatFooterTimestamp(value: Date): string {
  return value.toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function buildFooterVersionLabel(health: SystemHealthResponse | null): string {
  if (health === null) {
    return "v1.0.0";
  }
  return health.identity.app_version;
}

function AppFooter({
  health,
  currentTime,
  onOpenHealth,
}: {
  health: SystemHealthResponse | null;
  currentTime: Date;
  onOpenHealth: () => void;
}) {
  return (
    <footer className="app-footer">
      <button className="app-footer__identity" type="button" onClick={onOpenHealth}>
        <span>ID edge</span>
        <strong>{health?.identity.edge_id ?? "EDGE in lettura"}</strong>
      </button>
      <div className="app-footer__item">
        <span>Data e ora</span>
        <strong>{formatFooterTimestamp(currentTime)}</strong>
      </div>
      <div className="app-footer__item">
        <span>Versione app</span>
        <strong>{buildFooterVersionLabel(health)}</strong>
      </div>
      <div className="app-footer__item app-footer__item--host">
        <span>Host</span>
        <strong>{health?.identity.hostname ?? "locale"}</strong>
      </div>
    </footer>
  );
}

function OperatorPlantCommandabilityPanel({
  fleetControl,
  health,
  loading,
  error,
  onOpenHealth,
}: {
  fleetControl: FleetControlStatus | null;
  health: SystemHealthResponse | null;
  loading: boolean;
  error: string | null;
  onOpenHealth: () => void;
}) {
  const snapshot = buildOperatorCommandabilitySnapshot(
    fleetControl,
    health,
    loading,
    error,
  );

  return (
    <section
      className={`stage-panel operator-commandability-panel operator-commandability-panel--${snapshot.state}`}
    >
      <div className="stage-header">
        <div>
          <p className="panel-kicker">Eseguibilita comandi</p>
          <h2>Impianto comandabile</h2>
          <p className="stage-copy">
            Stato sintetico prima del prossimo setpoint: readiness, polling, compatibilita e piano
            broadcast.
          </p>
        </div>
        <div className="stage-header-actions">
          <span
            className={`operator-commandability-badge operator-commandability-badge--${snapshot.state}`}
          >
            {snapshot.answer}
          </span>
          <button className="secondary-button" type="button" onClick={onOpenHealth}>
            Health
          </button>
        </div>
      </div>

      <div className="operator-commandability-layout">
        <article className="operator-commandability-hero">
          <span>Stato</span>
          <strong>{snapshot.headline}</strong>
          <p>{snapshot.detail}</p>
          {snapshot.issues.length > 0 ? (
            <div className="operator-commandability-issues">
              {snapshot.issues.map((issue) => (
                <span key={issue}>{issue}</span>
              ))}
            </div>
          ) : null}
        </article>

        <div className="operator-commandability-metrics">
          {snapshot.metrics.map((metric) => (
            <article
              key={metric.label}
              className={`operator-commandability-metric operator-commandability-metric--${metric.tone}`}
            >
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <small>{metric.note}</small>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function OperatorCommandAuditPanel({
  fleetControl,
  onOpenHistory,
}: {
  fleetControl: FleetControlStatus | null;
  onOpenHistory: () => void;
}) {
  const results = (fleetControl?.last_device_results ?? [])
    .slice()
    .sort((left, right) => {
      const leftTime = new Date(left.timestamp).getTime();
      const rightTime = new Date(right.timestamp).getTime();
      return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
    });
  const lastDispatchAt = formatRuntimeTimestamp(fleetControl?.last_dispatch_at);
  const latencyLabel =
    fleetControl?.last_dispatch_latency_ms != null
      ? `${integerFormatter.format(fleetControl.last_dispatch_latency_ms)} ms`
      : "n.d.";

  return (
    <section className="stage-panel operator-command-audit-panel">
      <div className="stage-header">
        <div>
          <p className="panel-kicker">Audit comandi</p>
          <h2>Ultimo dispatch</h2>
          <p className="stage-copy">
            Lettura sintetica dell'ultimo invio: esiti, endpoint e comandi risolti dal runtime.
          </p>
        </div>
        <div className="stage-header-actions">
          <span className="operator-command-audit-latency">{latencyLabel}</span>
          <button className="secondary-button" type="button" onClick={onOpenHistory}>
            Storico
          </button>
        </div>
      </div>

      <div className="operator-command-audit-summary">
        <span>{lastDispatchAt ? `Ultimo invio ${lastDispatchAt}` : "Nessun dispatch letto"}</span>
        <span>{fleetControl ? `${fleetControl.last_dispatch_ok_count} ok` : "-- ok"}</span>
        <span>{fleetControl ? `${fleetControl.last_dispatch_error_count} errori` : "-- errori"}</span>
        <span>
          {fleetControl ? `${fleetControl.last_dispatch_skipped_count} saltati` : "-- saltati"}
        </span>
      </div>

      {results.length > 0 ? (
        <div className="operator-command-audit-list">
          {results.slice(0, 5).map((result) => {
            const timestamp = formatRuntimeTimestamp(result.timestamp) ?? result.timestamp;
            const endpointType = getDispatchDiagnosticText(
              result.diagnostics,
              "broadcast_endpoint_type",
            );
            return (
              <article
                key={`${result.device_id}:${result.timestamp}`}
                className={`operator-command-audit-item operator-command-audit-item--${result.outcome}`}
              >
                <div className="operator-command-audit-item__head">
                  <strong>{result.name}</strong>
                  <span>{translateDispatchOutcome(result.outcome)}</span>
                </div>
                <p>{result.message}</p>
                <div className="operator-command-audit-item__meta">
                  <span>{result.command ?? "Comando n.d."}</span>
                  <span>{buildDispatchEndpointLabel(result)}</span>
                  {endpointType ? <span>{endpointType}</span> : null}
                  <span>{timestamp}</span>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="operator-timeline-empty">
          L'audit si popola dopo il primo setpoint inviato dal runtime locale.
        </div>
      )}
    </section>
  );
}

function buildBroadcastGroupTone(group: SystemHealthBroadcastGroup): SummaryTone {
  if (group.state === "ready") {
    return "positive";
  }
  if (group.state === "blocked" || group.state === "warning") {
    return "warning";
  }
  return "neutral";
}

function buildBroadcastGroupModeLabel(group: SystemHealthBroadcastGroup): string {
  switch (group.broadcast_mode) {
    case "rtu_serial":
      return "RTU seriale";
    case "rtu_over_tcp":
      return "RTU-over-TCP";
    case "modbus_tcp":
      return "Modbus TCP";
    default:
      return "Per-device";
  }
}

function buildBroadcastGroupDryRun(group: SystemHealthBroadcastGroup): string {
  if (group.state === "ready") {
    return `Dry-run: una write broadcast su ${group.endpoint_label} per ${group.device_count} device.`;
  }
  if (group.state === "warning") {
    return "Dry-run: broadcast possibile, ma richiede verifica della suddivisione modelli.";
  }
  if (group.state === "blocked") {
    return "Dry-run: fallback per-device, nessuna write broadcast su questo endpoint.";
  }
  return "Dry-run: endpoint dedicato, comando singolo.";
}

function OperatorBroadcastTopologyPanel({
  health,
  onOpenHealth,
}: {
  health: SystemHealthResponse | null;
  onOpenHealth: () => void;
}) {
  const groups = (health?.broadcast_groups ?? [])
    .slice()
    .sort((left, right) => {
      const priority = { blocked: 0, warning: 1, ready: 2, not_applicable: 3 };
      const priorityDelta = priority[left.state] - priority[right.state];
      if (priorityDelta !== 0) {
        return priorityDelta;
      }
      return right.device_count - left.device_count;
    });
  const readyCount = groups.filter((group) => group.state === "ready").length;
  const attentionCount = groups.filter(
    (group) => group.state === "blocked" || group.state === "warning",
  ).length;

  return (
    <section className="stage-panel operator-broadcast-panel">
      <div className="stage-header">
        <div>
          <p className="panel-kicker">Topologia comandi</p>
          <h2>Piano broadcast</h2>
          <p className="stage-copy">
            Dry-run del prossimo setpoint in base a COM, gateway, unit e profili comando.
          </p>
        </div>
        <div className="stage-header-actions">
          <span className={`operator-broadcast-summary ${attentionCount > 0 ? "operator-broadcast-summary--warning" : ""}`}>
            {readyCount} pronti | {attentionCount} da verificare
          </span>
          <button className="secondary-button" type="button" onClick={onOpenHealth}>
            Dettagli
          </button>
        </div>
      </div>

      {groups.length > 0 ? (
        <div className="operator-broadcast-list">
          {groups.slice(0, 4).map((group) => {
            const tone = buildBroadcastGroupTone(group);
            const firstIssue = group.issues[0];
            return (
              <article
                key={`${group.endpoint_type}:${group.endpoint_label}`}
                className={`operator-broadcast-item operator-broadcast-item--${tone}`}
              >
                <div className="operator-broadcast-item__head">
                  <div>
                    <p>{buildBroadcastGroupModeLabel(group)}</p>
                    <strong>{group.endpoint_label}</strong>
                  </div>
                  <span>{group.state === "ready" ? "broadcast" : group.state}</span>
                </div>
                <p className="operator-broadcast-item__dry-run">
                  {buildBroadcastGroupDryRun(group)}
                </p>
                <div className="operator-broadcast-item__meta">
                  <span>{group.online_count}/{group.device_count} online</span>
                  <span>{group.model_count} modelli</span>
                  <span>{group.command_profile_count} profili comando</span>
                </div>
                {firstIssue ? (
                  <p className="operator-broadcast-item__issue">{firstIssue}</p>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <div className="detail-empty">
          Nessun endpoint Modbus condiviso da valutare per broadcast.
        </div>
      )}
    </section>
  );
}

function buildDeviceOperationalGuidance(
  device: Device,
  overview: DeviceOverview | null,
): OperationalGuidance {
  const lastError = overview?.diagnostics.last_error?.trim() ?? "";
  const normalizedError = lastError.toLowerCase();
  const deviceStatus = device.status.toLowerCase();
  const lastValidDataAt = formatRuntimeTimestamp(overview?.diagnostics.last_valid_data_at);
  const lastContactAt = formatRuntimeTimestamp(overview?.diagnostics.last_contact_at);

  if (deviceStatus === "online") {
    if (overview === null) {
      return {
        value: "Attendere conferma live",
        note: "Il device risulta online, ma la diagnostica dettagliata non e ancora disponibile.",
        tone: "neutral",
      };
    }

    if (overview.diagnostics.response_time_ms >= 2000) {
      return {
        value: "Monitorare latenza",
        note: `L'ultimo polling e riuscito, ma la risposta e stata di ${overview.diagnostics.response_time_ms} ms.`,
        tone: "neutral",
      };
    }

    return {
      value: "Nessuna azione",
      note: "Comunicazione stabile nell'ultimo polling utile.",
      tone: "positive",
    };
  }

  if (deviceStatus === "degraded") {
    return {
      value: "Comunicazione parziale",
      note: lastValidDataAt
        ? `Il device risponde ancora, ma l'ultimo dataset completo disponibile e del ${lastValidDataAt}.${lastContactAt ? ` Ultimo contatto ${lastContactAt}.` : ""}`
        : "Il device sta rispondendo solo in modo parziale: attendere una telemetria completa o verificare il bus.",
      tone: "warning",
    };
  }

  if (deviceStatus === "pending") {
    return {
      value: "Attendere il primo polling",
      note: "Il device e configurato ma non ha ancora completato una lettura utile.",
      tone: "neutral",
    };
  }

  if (normalizedError.includes("timeout")) {
    return {
      value: "Verificare rete o bus",
      note: lastError,
      tone: "warning",
    };
  }

  if (normalizedError.includes("unable to connect") || normalizedError.includes("connection")) {
    return {
      value: "Controllare endpoint",
      note: lastError,
      tone: "warning",
    };
  }

  if (
    normalizedError.includes("profile") ||
    normalizedError.includes("protocol") ||
    normalizedError.includes("register")
  ) {
    return {
      value: "Rivedere profilo",
      note: lastError,
      tone: "warning",
    };
  }

  if (lastError) {
    return {
      value: "Verificare comunicazione",
      note: lastError,
      tone: "warning",
    };
  }

  if (deviceStatus === "fault") {
    return {
      value: "Verificare device",
      note: "Il backend segnala un guasto operativo da approfondire.",
      tone: "warning",
    };
  }

  if (deviceStatus === "warning") {
    return {
      value: "Controllare diagnostica",
      note: "Il device e raggiungibile, ma richiede una verifica operativa.",
      tone: "warning",
    };
  }

  return {
    value: "Verificare dispositivo",
    note: "Serve un nuovo polling utile per confermare lo stato operativo.",
    tone: "warning",
  };
}

function buildLiveFocusItems(
  devices: Device[],
  powerMap: DevicePowerMap,
  selectedDevice: Device | null,
  selectedOverview: DeviceOverview | null,
): LiveFocusItem[] {
  if (selectedDevice !== null) {
    const guidance = buildDeviceOperationalGuidance(selectedDevice, selectedOverview);
    const monitoringNote = selectedOverview?.diagnostics.last_poll_status
      ? `Ultimo esito: ${selectedOverview.diagnostics.last_poll_status}`
      : selectedOverview
        ? `Risposta ${selectedOverview.diagnostics.response_time_ms} ms nell'ultimo polling utile.`
        : selectedDevice.status.toLowerCase() === "pending"
          ? "In attesa del primo polling utile."
          : "Diagnostica live non ancora disponibile.";

    return [
      {
        label: "Profilo attivo",
        value: `${selectedDevice.protocol} | ${selectedDevice.transport}`,
        note: `${selectedDevice.brand} | ${selectedDevice.model}`,
        tone: "neutral",
      },
      {
        label: "Stato monitoraggio",
        value: translateStatusLabel(selectedDevice.status),
        note: monitoringNote,
        tone: getStatusTone(selectedDevice.status),
      },
      {
        label: "Azione consigliata",
        value: guidance.value,
        note: guidance.note,
        tone: guidance.tone,
      },
    ];
  }

  return devices
    .slice()
    .sort((left, right) => {
      const statusDelta = getStatusPriority(right.status) - getStatusPriority(left.status);
      if (statusDelta !== 0) {
        return statusDelta;
      }

      return (powerMap[right.device_id] ?? Number.NEGATIVE_INFINITY) -
        (powerMap[left.device_id] ?? Number.NEGATIVE_INFINITY);
    })
    .slice(0, 3)
    .map((device) => ({
      label: device.name,
      value: translateStatusLabel(device.status),
      note: `${device.brand} | ${device.model} · ${formatSidebarPower(powerMap[device.device_id])}`,
      tone: getStatusTone(device.status),
    }));
}

function LiveFocusCard({ label, value, note, tone }: LiveFocusItem) {
  return (
    <article className={`live-focus-card live-focus-card--${tone}`}>
      <div className="live-focus-top">
        <p className="live-focus-label">{label}</p>
        <strong className="live-focus-value">{value}</strong>
      </div>
      <p className="live-focus-note">{note}</p>
    </article>
  );
}

function FocusPanelContent({
  selectedDevice,
  railSummaryItems,
  liveFocusItems,
  onClose,
}: {
  selectedDevice: Device | null;
  railSummaryItems: SummaryItem[];
  liveFocusItems: LiveFocusItem[];
  onClose: () => void;
}) {
  return (
    <div className="focus-drawer-shell">
      <header className="focus-drawer-header">
        <div>
          <p className="panel-kicker">
            {selectedDevice ? "Dispositivo in focus" : "Quadro impianto"}
          </p>
          <h2>{selectedDevice ? "Contesto operativo live" : "Riepilogo operativo"}</h2>
          <p className="focus-drawer-copy">
            {selectedDevice
              ? "Diagnostica, profilo e ultimo esito restano disponibili solo quando servono."
              : "Indicatori sintetici e asset in evidenza in una vista tecnica separata."}
          </p>
        </div>
        <button className="icon-button" type="button" onClick={onClose}>
          Chiudi
        </button>
      </header>

      <section className="rail-panel rail-panel--compact">
        <div className="rail-section-header">
          <div>
            <p className="panel-kicker">
              {selectedDevice ? "Contesto operativo" : "Sintesi impianto"}
            </p>
            <h2>{selectedDevice ? "Metriche tecniche" : "Metriche di riepilogo"}</h2>
          </div>
          <span className="panel-meta">
            {selectedDevice
              ? "Stato, tempi, tentativi e disponibilita comandi"
              : "Indicatori sintetici della situazione corrente"}
          </span>
        </div>
        <div className="rail-summary-grid" aria-label="Metriche di riepilogo">
          {railSummaryItems.map((item) => (
            <SummaryCard key={item.label} {...item} />
          ))}
        </div>
      </section>

      <section className="rail-panel rail-panel--compact">
        <div className="rail-section-header">
          <div>
            <p className="panel-kicker">Focus live</p>
            <h2>{selectedDevice ? "Segnali del dispositivo" : "Asset da tenere d'occhio"}</h2>
          </div>
          <span className="panel-meta">
            {selectedDevice
              ? "Ultimi indicatori significativi dal backend"
              : "Classifica rapida degli asset piu rilevanti"}
          </span>
        </div>

        <div className="live-focus-list">
          {liveFocusItems.map((item) => (
            <LiveFocusCard key={item.label} {...item} />
          ))}
        </div>
      </section>
    </div>
  );
}

function formatSidebarPower(powerKw: number | null | undefined): string {
  if (powerKw === null || powerKw === undefined) {
    return "n.d.";
  }

  return `${metricFormatter.format(powerKw)} kW`;
}

function DeviceSidebarItem({
  active,
  device,
  overview,
  currentPower,
  onSelect,
  onOpenSettings,
  showManageAction = true,
  actionLabel = "Gestisci",
}: {
  active: boolean;
  device: Device;
  overview: DeviceOverview | null;
  currentPower: number | null | undefined;
  onSelect: () => void;
  onOpenSettings: () => void;
  showManageAction?: boolean;
  actionLabel?: string;
}) {
  const lastContactAt = formatRuntimeTimestamp(overview?.diagnostics.last_contact_at);
  const lastValidDataAt = formatRuntimeTimestamp(overview?.diagnostics.last_valid_data_at);
  const hasDistinctLastValidDataAt =
    lastValidDataAt !== null && lastValidDataAt !== lastContactAt;

  return (
    <article className={`sidebar-device ${active ? "sidebar-device--active" : ""}`}>
      <button className="sidebar-device-main" type="button" onClick={onSelect}>
        <div className="sidebar-device-top">
          <div>
            <strong className="sidebar-device-name">{device.name}</strong>
            <span className="sidebar-device-caption">
              {device.brand} | {device.model}
            </span>
          </div>
          <StatusBadge status={device.status} />
        </div>
        <div className="sidebar-device-bottom">
          <span className="sidebar-device-meta">
            {device.protocol} | {device.transport}
          </span>
          <strong className="sidebar-device-power">
            {formatSidebarPower(currentPower)}
          </strong>
        </div>
        {lastContactAt ? (
          <div className="sidebar-device-note">Ultimo contatto {lastContactAt}</div>
        ) : lastValidDataAt ? (
          <div className="sidebar-device-note">Ultimo dato valido {lastValidDataAt}</div>
        ) : null}
        {hasDistinctLastValidDataAt ? (
          <div className="sidebar-device-note sidebar-device-note--secondary">
            Dato valido {lastValidDataAt}
          </div>
        ) : null}
      </button>
      {showManageAction ? (
        <div className="sidebar-device-actions">
          <button className="sidebar-device-action" type="button" onClick={onOpenSettings}>
            {actionLabel}
          </button>
        </div>
      ) : null}
    </article>
  );
}

function StatusBadge({ status }: { status: string }) {
  const normalizedStatus = status.toLowerCase();
  return (
    <span className={`status-badge status-badge--${normalizedStatus}`}>
      {translateStatusLabel(status)}
    </span>
  );
}

function MobileStageTabs({
  tabs,
  activeTab,
  onChange,
}: {
  tabs: StageTabOption[];
  activeTab: MobileStageTab;
  onChange: (tab: MobileStageTab) => void;
}) {
  return (
    <nav className="mobile-stage-nav" aria-label="Navigazione contenuti dispositivo">
      <div className="mobile-stage-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={`mobile-stage-tab ${
              activeTab === tab.key ? "mobile-stage-tab--active" : ""
            }`}
            type="button"
            onClick={() => onChange(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </nav>
  );
}

function FleetSidebarContent({
  summary,
  loading,
  error,
  availability,
  devices,
  selectedDeviceId,
  devicePowerMap,
  deviceOverviewMap,
  onAddDevice,
  onOpenDiscovery,
  onSelectFleet,
  onSelectDevice,
  onOpenSettings,
  discoveryActive,
  discoveryResultCount,
  onClose,
  viewMode = "pro",
}: {
  summary: DashboardSummary | null;
  loading: boolean;
  error: string | null;
  availability: number;
  devices: Device[];
  selectedDeviceId: string | null;
  devicePowerMap: DevicePowerMap;
  deviceOverviewMap: DeviceOverviewMap;
  onAddDevice: () => void;
  onOpenDiscovery: () => void;
  onSelectFleet: () => void;
  onSelectDevice: (deviceId: string) => void;
  onOpenSettings: (deviceId: string) => void;
  discoveryActive: boolean;
  discoveryResultCount: number;
  onClose?: () => void;
  viewMode?: DashboardMode;
}) {
  const isLiteView = viewMode === "lite";
  const availabilityRatio =
    summary && summary.total_devices > 0
      ? `${summary.online_devices}/${summary.total_devices} online`
      : devices.length > 0
        ? `0/${devices.length} online`
        : "--/-- online";

  return (
    <>
      <SidebarBrandMark header />
      <div className="sidebar-header">
        <div>
          <p className="panel-kicker">
            {isLiteView ? "Dashboard Lite" : "Dispositivi di campo"}
          </p>
          <h2>{isLiteView ? "Albero dispositivi" : "Parco inverter"}</h2>
        </div>
        <div className="sidebar-header-actions">
          {onClose ? (
            <button className="icon-button" type="button" onClick={onClose}>
              Chiudi
            </button>
          ) : null}
          {!isLiteView ? (
            <>
              <button className="secondary-button" type="button" onClick={onOpenDiscovery}>
                Browsing
                {discoveryResultCount > 0 ? (
                  <span className="button-counter-badge">{discoveryResultCount}</span>
                ) : null}
              </button>
              <button
                className={`action-button ${discoveryActive ? "action-button--busy" : ""}`}
                type="button"
                onClick={onAddDevice}
              >
                Aggiungi dispositivo
                {discoveryActive ? <span className="button-activity-dot" aria-hidden="true" /> : null}
              </button>
            </>
          ) : null}
        </div>
      </div>

      <button
        className={`sidebar-device sidebar-device--fleet ${
          selectedDeviceId ? "" : "sidebar-device--active"
        }`}
        type="button"
        onClick={onSelectFleet}
      >
        <div className="sidebar-device-top">
          <div>
            <strong className="sidebar-device-name">Vista impianto</strong>
            <span className="sidebar-device-caption">Panoramica generale del parco inverter</span>
          </div>
          <span className="sidebar-overview-chip">
            {summary ? `${summary.total_devices} dispositivi` : "--"}
          </span>
        </div>
        <div className="sidebar-device-bottom">
          <div>
            <span className="sidebar-device-meta">Disponibilita operativa</span>
            <span className="sidebar-device-caption">{availabilityRatio}</span>
          </div>
          <strong className="sidebar-device-power">
            {loading ? "..." : error ? "--" : `${availability}%`}
          </strong>
        </div>
      </button>

      <div className="sidebar-device-list">
        {devices.length > 0 ? (
          devices.map((device) => (
            <DeviceSidebarItem
              key={device.device_id}
              active={device.device_id === selectedDeviceId}
              device={device}
              overview={deviceOverviewMap[device.device_id] ?? null}
              currentPower={devicePowerMap[device.device_id]}
              onSelect={() => onSelectDevice(device.device_id)}
              onOpenSettings={() => onOpenSettings(device.device_id)}
              showManageAction={!isLiteView}
              actionLabel={isLiteView ? "Dettaglio" : "Gestisci"}
            />
          ))
        ) : (
          <div className="sidebar-empty">
            {loading
              ? "Caricamento dispositivi..."
              : error
                ? "Parco inverter non disponibile."
                : "Nessun dispositivo configurato."}
          </div>
        )}
      </div>
    </>
  );
}

function SidebarBrandMark({
  compact = false,
  header = false,
}: {
  compact?: boolean;
  header?: boolean;
}) {
  return (
    <div
      className={`sidebar-brand-mark ${compact ? "sidebar-brand-mark--compact" : ""} ${
        header ? "sidebar-brand-mark--header" : ""
      }`}
      aria-hidden="true"
    >
      <img src="/logo_HBA_STE.png" alt="" />
    </div>
  );
}

function formatConnectionSettings(connectionSettings: Device["connection_settings"]): string {
  const entries = Object.entries(connectionSettings);
  if (entries.length === 0) {
    return "Nessuna impostazione";
  }

  return entries
    .slice(0, 2)
    .map(([key, value]) => {
      const displayValue =
        key === "port" && typeof value === "string"
          ? getSerialPortDisplayName(value)
          : String(value);
      return `${key}: ${displayValue}`;
    })
    .join(" / ");
}

function formatCreatedAt(createdAt: string): string {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) {
    return createdAt;
  }

  return dateTimeFormatter.format(date);
}

function DataGroupCard({ group }: { group: DataGroup }) {
  return (
    <article className="group-card">
      <p className="group-card-title">{group.title}</p>
      <strong className="group-card-value">{group.value}</strong>
      <p className="group-card-note">{group.note}</p>
      <div className="group-card-list">
        {group.rows.map((row) => (
          <div key={row.label} className="group-card-row">
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </div>
        ))}
      </div>
    </article>
  );
}

function buildTelemetryGroups(overview: DeviceOverview): DataGroup[] {
  return buildOrderedTelemetrySections(overview.telemetry)
    .slice(0, 3)
    .map(({ section, points }) => ({
      title: translateTelemetrySection(section),
      value: points[0]
        ? points[0].unit
          ? `${points[0].display_value} ${points[0].unit}`
          : points[0].display_value
        : "--",
      note: buildTelemetrySectionNote(section),
      rows: points.slice(0, 3).map((point) => ({
        label: translateTelemetryLabel(point.label),
        value: point.unit ? `${point.display_value} ${point.unit}` : point.display_value,
      })),
    }));
}

function buildFleetGroups(
  summary: DashboardSummary | null,
  referenceOverview: DeviceOverview | null,
): DataGroup[] {
  const dcSignals = pickTelemetrySignals(referenceOverview, DC_SIGNAL_DEFINITIONS);
  const acSignals = pickTelemetrySignals(referenceOverview, AC_SIGNAL_DEFINITIONS);

  return [
    {
      title: "Produzione impianto",
      value: summary ? `${metricFormatter.format(summary.total_power_kw)} kW` : "--",
      note: "Sintesi della resa complessiva disponibile nell'ultimo ciclo utile.",
      rows: [
        {
          label: "Potenza nominale",
          value: summary ? formatCompactPowerKw(summary.nominal_power_kw) : "--",
        },
        {
          label: "Utilizzo nominale",
          value:
            summary?.power_utilization_percent != null
              ? `${metricFormatter.format(summary.power_utilization_percent)}%`
              : "--",
        },
        {
          label: "Energia giornaliera",
          value: summary ? `${metricFormatter.format(summary.daily_energy_kwh)} kWh` : "--",
        },
        {
          label: "Energia totale",
          value: summary ? `${metricFormatter.format(summary.total_energy_kwh)} kWh` : "--",
        },
      ],
    },
    {
      title: "Quadro rete AC",
      value: acSignals[0]?.value ?? "n.d.",
      note: "Riferimento elettrico lato rete ricavato dal device live piu attendibile.",
      rows: acSignals.map((signal) => ({
        label: signal.label,
        value: signal.value,
      })),
    },
    {
      title: "Campo FV e DC",
      value: dcSignals[0]?.value ?? "n.d.",
      note: "Indicatori lato campo e accumulo dal riferimento live scelto automaticamente.",
      rows: dcSignals.map((signal) => ({
        label: signal.label,
        value: signal.value,
      })),
    },
    {
      title: "Stato e allarmi",
      value: summary ? integerFormatter.format(summary.active_alarms) : "--",
      note: "Disponibilita operativa, allarmi attivi e continuita del monitoraggio.",
      rows: [
        {
          label: "Dispositivi online",
          value: summary ? integerFormatter.format(summary.online_devices) : "--",
        },
        {
          label: "Dispositivi offline",
          value: summary ? integerFormatter.format(summary.offline_devices) : "--",
        },
        {
          label: "Allarmi attivi",
          value: summary ? integerFormatter.format(summary.active_alarms) : "--",
        },
        {
          label: "Disponibilita",
          value:
            summary && summary.total_devices > 0
              ? `${Math.round((summary.online_devices / summary.total_devices) * 100)}%`
              : "--",
        },
      ],
    },
  ];
}

function buildDeviceGroups(device: Device, overview: DeviceOverview | null): DataGroup[] {
  if (overview && overview.telemetry.length > 0) {
    return [
      {
        title: "Produzione",
        value: `${metricFormatter.format(overview.metrics.power_kw)} kW`,
        note: "Sintesi operativa del dispositivo selezionato.",
        rows: [
          {
            label: "Energia oggi",
            value: `${metricFormatter.format(overview.metrics.daily_energy_kwh)} kWh`,
          },
          {
            label: "Energia totale",
            value: `${metricFormatter.format(overview.metrics.total_energy_kwh)} kWh`,
          },
          {
            label: "Temperatura",
            value: `${metricFormatter.format(overview.metrics.temperature_c)} C`,
          },
        ],
      },
      ...buildTelemetryGroups(overview).slice(0, 2),
      {
        title: "Diagnostica",
        value: translateStatusLabel(device.status),
        note: "Polling, recovery e ultimo esito del backend.",
        rows: [
          {
            label: "Ultimo dato valido",
            value: formatRuntimeTimestamp(overview.diagnostics.last_valid_data_at) ?? "non disponibile",
          },
          {
            label: "Ultimo contatto",
            value: formatRuntimeTimestamp(overview.diagnostics.last_contact_at) ?? "non disponibile",
          },
          { label: "Tempo di risposta", value: `${overview.diagnostics.response_time_ms} ms` },
          { label: "Tentativi", value: String(overview.diagnostics.retries) },
          {
            label: "Ultimo errore",
            value: overview.diagnostics.last_error ?? "nessuno",
          },
        ],
      },
    ];
  }

  return [
    {
      title: "Produzione",
      value: translateStatusLabel(device.status),
      note: "Il dispositivo e configurato ma non ha ancora restituito dati completi.",
      rows: [
        { label: "Dispositivo", value: device.name },
        { label: "Marchio", value: device.brand },
        { label: "Modello", value: device.model },
        {
          label: "Ultimo dato valido",
          value: overview
            ? formatRuntimeTimestamp(overview.diagnostics.last_valid_data_at) ?? "non disponibile"
            : "non disponibile",
        },
      ],
    },
    {
      title: "Connessione",
      value: `${device.protocol} | ${device.transport}`,
      note: "Profilo di comunicazione attualmente selezionato.",
      rows: [
        { label: "Protocollo", value: device.protocol },
        { label: "Trasporto", value: device.transport },
        { label: "Stato operativo", value: translateStatusLabel(device.status) },
      ],
    },
    {
      title: "Profilo",
      value: formatCreatedAt(device.created_at),
      note: "Contesto base disponibile prima della prima telemetria utile.",
      rows: [
        { label: "Creato il", value: formatCreatedAt(device.created_at) },
        { label: "Connessione", value: formatConnectionSettings(device.connection_settings) },
        { label: "Provisioning", value: "completato" },
      ],
    },
  ];
}

function buildFleetChartSeries(
  powerHistory: FleetPowerHistoryResponse | null,
): PowerHistoryChartSeries[] {
  if (powerHistory === null) {
    return [];
  }

  return [
    ...powerHistory.device_series.map((series) => ({
      id: series.device_id ?? series.label,
      label: series.label,
      timestamps: series.timestamps,
      values: series.values,
    })),
    {
      id: powerHistory.total_series.device_id ?? "fleet-total",
      label: powerHistory.total_series.label,
      timestamps: powerHistory.total_series.timestamps,
      values: powerHistory.total_series.values,
      emphasis: true,
      color: "#5cd4bd",
    },
  ];
}

function buildLiteFleetChartSeries(
  powerHistory: FleetPowerHistoryResponse | null,
): PowerHistoryChartSeries[] {
  if (powerHistory === null) {
    return [];
  }

  return [
    {
      id: powerHistory.total_series.device_id ?? "fleet-total-lite",
      label: powerHistory.total_series.label,
      timestamps: powerHistory.total_series.timestamps,
      values: powerHistory.total_series.values,
      emphasis: true,
      color: "#5cd4bd",
    },
  ];
}

function AppActionDialog({
  open,
  title,
  message,
  tone,
  confirmLabel,
  onConfirm,
  onClose,
  cancelLabel,
  busy = false,
  confirmVariant = "accent",
}: {
  open: boolean;
  title: string;
  message: string;
  tone: AppDialogTone;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  cancelLabel?: string;
  busy?: boolean;
  confirmVariant?: "accent" | "danger";
}) {
  if (!open) {
    return null;
  }

  const toneLabel =
    tone === "error"
      ? "Errore"
      : tone === "warning"
        ? "Conferma"
        : tone === "success"
          ? "Completato"
          : "Notifica";

  return (
    <div
      className="app-dialog-backdrop"
      onClick={() => {
        if (!busy) {
          onClose();
        }
      }}
    >
      <aside
        aria-modal="true"
        aria-labelledby="app-action-dialog-title"
        className="modal-panel modal-panel--compact app-dialog-panel"
        role="dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div className="modal-title-group">
            <span className={`app-dialog-tone app-dialog-tone--${tone}`}>{toneLabel}</span>
            <h2 id="app-action-dialog-title">{title}</h2>
            <p className="modal-copy">{message}</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} disabled={busy}>
            Chiudi
          </button>
        </div>
        <div className="app-dialog-body">
          <div className="confirm-actions">
            {cancelLabel ? (
              <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
                {cancelLabel}
              </button>
            ) : null}
            <button
              className={confirmVariant === "danger" ? "danger-button" : "action-button"}
              type="button"
              onClick={onConfirm}
              disabled={busy}
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}

export default function App() {
  const [viewportWidth, setViewportWidth] = useState<number>(() =>
    typeof window === "undefined" ? 1440 : window.innerWidth,
  );
  const [footerTime, setFooterTime] = useState(() => new Date());
  const [dashboardMode, setDashboardMode] = useState<DashboardMode>("operator");
  const [solarBackgroundEnabled, setSolarBackgroundEnabled] = useState(
    readStoredSolarBackgroundEnabled,
  );
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [fleetControl, setFleetControl] = useState<FleetControlStatus | null>(null);
  const [systemHealth, setSystemHealth] = useState<SystemHealthResponse | null>(null);
  const [systemHealthError, setSystemHealthError] = useState<string | null>(null);
  const [devicePowerMap, setDevicePowerMap] = useState<DevicePowerMap>({});
  const [deviceOverviewMap, setDeviceOverviewMap] = useState<DeviceOverviewMap>({});
  const [powerHistory, setPowerHistory] = useState<FleetPowerHistoryResponse | null>(null);
  const [powerHistoryError, setPowerHistoryError] = useState<string | null>(null);
  const [powerHistoryRange, setPowerHistoryRange] = useState<PowerHistoryRangeSelection>(() =>
    buildPresetPowerHistoryRange(DEFAULT_POWER_HISTORY_RANGE_PRESET),
  );
  const [isAddDeviceOpen, setIsAddDeviceOpen] = useState(false);
  const [isDiscoveryOpen, setIsDiscoveryOpen] = useState(false);
  const [isDiscoveryRunning, setIsDiscoveryRunning] = useState(false);
  const [discoveryResultCount, setDiscoveryResultCount] = useState(0);
  const [addDevicePrefill, setAddDevicePrefill] = useState<DeviceDiscoveryPrefill | null>(null);
  const [isFleetDrawerOpen, setIsFleetDrawerOpen] = useState(false);
  const [isFocusPanelOpen, setIsFocusPanelOpen] = useState(false);
  const [isSystemHealthOpen, setIsSystemHealthOpen] = useState(false);
  const [isSystemSettingsOpen, setIsSystemSettingsOpen] = useState(false);
  const [isOperatorProvisioningOpen, setIsOperatorProvisioningOpen] = useState(false);
  const [isAdvancedFleetHistoryOpen, setIsAdvancedFleetHistoryOpen] = useState(false);
  const [mobileStageTab, setMobileStageTab] = useState<MobileStageTab>("live");
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [settingsDeviceId, setSettingsDeviceId] = useState<string | null>(null);
  const [isLiteSidebarExpanded, setIsLiteSidebarExpanded] = useState(true);
  const [isOperatorSettingsPageOpen, setIsOperatorSettingsPageOpen] = useState(false);
  const [isOperatorControlAuditPageOpen, setIsOperatorControlAuditPageOpen] = useState(false);
  const [isOperatorComSettingsOpen, setIsOperatorComSettingsOpen] = useState(false);
  const [operatorComSettingsFocus, setOperatorComSettingsFocus] =
    useState<OperatorComSettingsSectionKey>("slave");
  const [operatorProvisioningProgress, setOperatorProvisioningProgress] =
    useState<OperatorProvisioningProgressState | null>(null);
  const [operatorProvisioningBusy, setOperatorProvisioningBusy] = useState(false);
  const [operatorScanBusy, setOperatorScanBusy] = useState(false);
  const [firstConnectWatch, setFirstConnectWatch] = useState<FirstConnectWatchState | null>(null);
  const [operatorProvisioningCancelRequestToken, setOperatorProvisioningCancelRequestToken] =
    useState(0);
  const [networkPendingChange, setNetworkPendingChange] = useState<PendingNetworkChange | null>(null);
  const [networkPendingActionBusy, setNetworkPendingActionBusy] =
    useState<"confirm" | "rollback" | null>(null);
  const [networkPendingActionError, setNetworkPendingActionError] = useState<string | null>(null);
  const [fleetSetpointInput, setFleetSetpointInput] = useState("");
  const [fleetSetpointInputDirty, setFleetSetpointInputDirty] = useState(false);
  const [fleetSetpointActionBusy, setFleetSetpointActionBusy] = useState(false);
  const [fleetSetpointActionError, setFleetSetpointActionError] = useState<string | null>(null);
  const [cciToggleBusy, setCciToggleBusy] = useState(false);
  const [cciToggleError, setCciToggleError] = useState<string | null>(null);
  const [slaveSettingsDraft, setSlaveSettingsDraft] = useState<ModbusSlaveSettingsDraft | null>(null);
  const [slaveSettingsBusy, setSlaveSettingsBusy] = useState(false);
  const [slaveSettingsDirty, setSlaveSettingsDirty] = useState(false);
  const [slaveSettingsError, setSlaveSettingsError] = useState<string | null>(null);
  const [slaveSettingsMessage, setSlaveSettingsMessage] = useState<string | null>(null);
  const [hsmBridgeSettingsDraft, setHsmBridgeSettingsDraft] =
    useState<HsmBridgeSettingsDraft | null>(null);
  const [hsmBridgeSettingsBusy, setHsmBridgeSettingsBusy] = useState(false);
  const [hsmBridgeSettingsDirty, setHsmBridgeSettingsDirty] = useState(false);
  const [hsmBridgeSettingsError, setHsmBridgeSettingsError] = useState<string | null>(null);
  const [hsmBridgeSettingsMessage, setHsmBridgeSettingsMessage] = useState<string | null>(null);
  const [serialPorts, setSerialPorts] = useState<SerialPortInfo[]>([]);
  const [deviceSetpointInput, setDeviceSetpointInput] = useState("");
  const [deviceSetpointActionBusy, setDeviceSetpointActionBusy] = useState(false);
  const [deviceSetpointActionError, setDeviceSetpointActionError] = useState<string | null>(null);
  const [deviceSetpointActionMessage, setDeviceSetpointActionMessage] = useState<string | null>(null);
  const [deleteAllDevicesBusy, setDeleteAllDevicesBusy] = useState(false);
  const [deleteDeviceBusyId, setDeleteDeviceBusyId] = useState<string | null>(null);
  const [deleteDialog, setDeleteDialog] = useState<DeleteDialogState | null>(null);
  const [noticeDialog, setNoticeDialog] = useState<NoticeDialogState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const isMountedRef = useRef(true);
  const requestInFlightRef = useRef(false);
  const fleetStatusRequestInFlightRef = useRef(false);
  const powerHistoryLoadedAtRef = useRef(0);
  const powerHistoryRangeRef = useRef<PowerHistoryRangeSelection>(powerHistoryRange);
  const overviewLoadedAtRef = useRef(0);
  const overviewPollingCycleRef = useRef<string | null>(null);
  const overviewDeviceSignatureRef = useRef("");
  const networkPendingResolutionRef = useRef<"confirm" | "rollback" | null>(null);

  const handleSolarBackgroundToggle = useCallback((enabled: boolean) => {
    setSolarBackgroundEnabled(enabled);
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(SOLAR_BACKGROUND_STORAGE_KEY, enabled ? "true" : "false");
      } catch {
        // Non blocca la UI se il browser impedisce la persistenza locale.
      }
    }
  }, []);

  function openManualAddDevice() {
    setAddDevicePrefill(null);
    setIsAddDeviceOpen(true);
  }

  function closeAddDevice() {
    setIsAddDeviceOpen(false);
    setAddDevicePrefill(null);
  }

  function openDiscoveryModal() {
    setIsDiscoveryOpen(true);
  }

  function handleDiscoverySelection(prefill: DeviceDiscoveryPrefill) {
    setAddDevicePrefill(prefill);
    setIsDiscoveryOpen(false);
    setIsAddDeviceOpen(true);
  }

  const handleNetworkPendingChange = useCallback((nextPendingChange: PendingNetworkChange | null) => {
    setNetworkPendingActionError(null);
    setNetworkPendingChange(nextPendingChange);
    if (nextPendingChange !== null) {
      networkPendingResolutionRef.current = null;
    }
  }, []);

  async function loadDeviceOverviews(nextDevices: Device[]) {
    if (nextDevices.length === 0) {
      if (isMountedRef.current) {
        setDevicePowerMap({});
        setDeviceOverviewMap({});
      }
      return;
    }

    const overviewEntries = await Promise.all(
      nextDevices.map(async (device): Promise<[string, DeviceOverview | null]> => {
        try {
          const overview = await getDeviceOverview(device.device_id, { refresh: false });
          return [device.device_id, overview];
        } catch {
          return [device.device_id, null];
        }
      }),
    );

    if (!isMountedRef.current) {
      return;
    }

    const nextOverviewMap = overviewEntries.reduce<DeviceOverviewMap>(
      (accumulator, [deviceId, overview]) => {
        accumulator[deviceId] = overview;
        return accumulator;
      },
      {},
    );
    const nextPowerMap = Object.entries(nextOverviewMap).reduce<DevicePowerMap>(
      (accumulator, [deviceId, overview]) => {
        accumulator[deviceId] = overview?.metrics.power_kw ?? null;
        return accumulator;
      },
      {},
    );
    setDeviceOverviewMap(nextOverviewMap);
    setDevicePowerMap(nextPowerMap);
  }

  async function loadDashboardData(showLoading = true) {
    if (requestInFlightRef.current) {
      return;
    }

    requestInFlightRef.current = true;
    if (showLoading) {
      setLoading(true);
    }
    setError(null);

    try {
      const currentPowerHistoryRange = powerHistoryRangeRef.current;
      const shouldRefreshPowerHistory =
        showLoading ||
        powerHistory === null ||
        (currentPowerHistoryRange.isLive &&
          Date.now() - powerHistoryLoadedAtRef.current >=
            getPowerHistoryRefreshMs(currentPowerHistoryRange.presetId));
      const [
        summaryResult,
        devicesResult,
        historyResult,
        fleetControlResult,
        systemHealthResult,
      ] = await Promise.allSettled([
        getDashboardSummary(),
        getDevices(),
        shouldRefreshPowerHistory
          ? getDashboardPowerHistory(buildPowerHistoryQuery(currentPowerHistoryRange))
          : Promise.resolve(null),
        getFleetControlStatus(),
        getSystemHealth(),
      ]);

      if (summaryResult.status === "rejected") {
        throw summaryResult.reason;
      }

      if (devicesResult.status === "rejected") {
        throw devicesResult.reason;
      }

      const nextSummary = summaryResult.value;
      const nextDevices = devicesResult.value;
      const nextPowerHistory = historyResult.status === "fulfilled" ? historyResult.value : null;
      const nextFleetControl =
        fleetControlResult.status === "fulfilled" ? fleetControlResult.value : null;
      const nextSystemHealth =
        systemHealthResult.status === "fulfilled" ? systemHealthResult.value : null;
      const nextPowerHistoryError =
        shouldRefreshPowerHistory && historyResult.status === "rejected"
          ? historyResult.reason instanceof Error
            ? historyResult.reason.message
            : "Impossibile caricare lo storico di potenza dell'impianto."
          : shouldRefreshPowerHistory
            ? null
            : powerHistoryError;
      const nextSystemHealthError =
        systemHealthResult.status === "rejected"
          ? systemHealthResult.reason instanceof Error
            ? systemHealthResult.reason.message
            : "Impossibile caricare l'health del sistema."
          : null;

      if (!isMountedRef.current) {
        return;
      }

      setSummary(nextSummary);
      setDevices(nextDevices);
      setFleetControl(nextFleetControl);
      setSystemHealth(nextSystemHealth);
      setSystemHealthError(nextSystemHealthError);
      if (shouldRefreshPowerHistory) {
        powerHistoryLoadedAtRef.current = Date.now();
        if (nextPowerHistory !== null) {
          setPowerHistory(nextPowerHistory);
        }
        setPowerHistoryError(nextPowerHistoryError);
      }

      const nowMs = Date.now();
      const nextOverviewCycle = nextSystemHealth?.polling.last_cycle_completed_at ?? null;
      const nextDeviceSignature = buildDeviceOverviewRefreshSignature(nextDevices);
      const shouldRefreshDeviceOverviews =
        showLoading ||
        nextDeviceSignature !== overviewDeviceSignatureRef.current ||
        (nextOverviewCycle !== null && nextOverviewCycle !== overviewPollingCycleRef.current) ||
        (nextOverviewCycle === null &&
          nowMs - overviewLoadedAtRef.current >= DASHBOARD_OVERVIEW_FALLBACK_REFRESH_MS);

      if (shouldRefreshDeviceOverviews) {
        overviewDeviceSignatureRef.current = nextDeviceSignature;
        overviewPollingCycleRef.current = nextOverviewCycle;
        overviewLoadedAtRef.current = nowMs;
        await loadDeviceOverviews(nextDevices);
      }
    } catch (loadError) {
      if (!isMountedRef.current) {
        return;
      }

      setDevicePowerMap({});
      setDeviceOverviewMap({});
      setPowerHistory(null);
      setPowerHistoryError(null);
      setFleetControl(null);
      setSystemHealth(null);
      setSystemHealthError(null);
      setSummary(null);
      setDevices([]);
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Impossibile caricare i dati dal backend.",
      );
    } finally {
      requestInFlightRef.current = false;
      if (isMountedRef.current && showLoading) {
        setLoading(false);
      }
    }
  }

  const refreshFleetControlStatus = useCallback(async () => {
    if (fleetStatusRequestInFlightRef.current) {
      return;
    }

    fleetStatusRequestInFlightRef.current = true;
    try {
      const nextFleetControl = await getFleetControlStatus();
      if (!isMountedRef.current) {
        return;
      }
      setFleetControl(nextFleetControl);
    } catch {
      // Manteniamo l'ultimo stato noto in UI per non introdurre flicker nei badge CCI.
    } finally {
      fleetStatusRequestInFlightRef.current = false;
    }
  }, []);

  async function refreshNetworkPendingChange() {
    try {
      const snapshot = await getNetworkConfiguration();
      if (!isMountedRef.current) {
        return;
      }
      if (snapshot.pending_change === null && networkPendingChange !== null) {
        const resolution = networkPendingResolutionRef.current;
        networkPendingResolutionRef.current = null;
        setNetworkPendingChange(null);
        setNetworkPendingActionError(null);
        if (resolution !== "confirm") {
          setIsSystemSettingsOpen(true);
        }
        return;
      }
      setNetworkPendingChange(snapshot.pending_change);
    } catch {
      // Keep the last pending snapshot visible; losing contact may be caused by the LAN change itself.
    }
  }

  async function handleConfirmNetworkChange() {
    setNetworkPendingActionBusy("confirm");
    setNetworkPendingActionError(null);
    networkPendingResolutionRef.current = "confirm";
    try {
      const snapshot = await confirmNetworkConfiguration();
      if (!isMountedRef.current) {
        return;
      }
      setNetworkPendingChange(snapshot.pending_change);
      if (snapshot.pending_change === null) {
        setNetworkPendingActionError(null);
      }
    } catch (actionError) {
      if (!isMountedRef.current) {
        return;
      }
      networkPendingResolutionRef.current = null;
      setNetworkPendingActionError(
        actionError instanceof Error
          ? actionError.message
          : "Impossibile confermare la modifica LAN.",
      );
      setIsSystemSettingsOpen(true);
    } finally {
      if (isMountedRef.current) {
        setNetworkPendingActionBusy(null);
      }
    }
  }

  async function handleRollbackNetworkChange() {
    setNetworkPendingActionBusy("rollback");
    setNetworkPendingActionError(null);
    networkPendingResolutionRef.current = "rollback";
    try {
      const snapshot = await rollbackNetworkConfiguration();
      if (!isMountedRef.current) {
        return;
      }
      setNetworkPendingChange(snapshot.pending_change);
      setIsSystemSettingsOpen(true);
    } catch (actionError) {
      if (!isMountedRef.current) {
        return;
      }
      networkPendingResolutionRef.current = null;
      setNetworkPendingActionError(
        actionError instanceof Error
          ? actionError.message
          : "Impossibile ripristinare la configurazione LAN.",
      );
      setIsSystemSettingsOpen(true);
    } finally {
      if (isMountedRef.current) {
        setNetworkPendingActionBusy(null);
      }
    }
  }

  function commitPowerHistoryRange(nextRange: PowerHistoryRangeSelection): void {
    powerHistoryRangeRef.current = nextRange;
    powerHistoryLoadedAtRef.current = 0;
    setPowerHistoryRange(nextRange);
    setPowerHistoryError(null);
    void loadDashboardData(false);
  }

  function handlePowerHistoryRangePresetChange(presetId: PowerHistoryRangePresetId): void {
    commitPowerHistoryRange(buildPresetPowerHistoryRange(presetId));
  }

  function handlePowerHistoryRangeShift(direction: -1 | 1): void {
    const currentRange = powerHistoryRangeRef.current;
    if (direction > 0 && currentRange.isLive) {
      return;
    }

    const durationMs = getPowerHistoryRangeDurationMs(currentRange);
    const currentEnd = currentRange.isLive ? new Date() : new Date(currentRange.endIso);
    const currentStart = new Date(currentEnd.getTime() - durationMs);
    const nextEnd =
      direction < 0
        ? currentStart
        : new Date(Math.min(Date.now(), currentEnd.getTime() + durationMs));
    const nextStart = new Date(nextEnd.getTime() - durationMs);
    const nextIsLive = nextEnd.getTime() >= Date.now() - 30_000;

    commitPowerHistoryRange({
      ...currentRange,
      startIso: nextStart.toISOString(),
      endIso: nextEnd.toISOString(),
      isLive: nextIsLive,
    });
  }

  function handlePowerHistoryJumpToLive(): void {
    const currentRange = powerHistoryRangeRef.current;
    const durationMs = getPowerHistoryRangeDurationMs(currentRange);
    const end = new Date();
    const start = new Date(end.getTime() - durationMs);

    commitPowerHistoryRange({
      ...currentRange,
      startIso: start.toISOString(),
      endIso: end.toISOString(),
      isLive: true,
    });
  }

  function handlePowerHistoryCustomRangeApply(startIso: string, endIso: string): void {
    commitPowerHistoryRange({
      ...powerHistoryRangeRef.current,
      mode: "custom",
      startIso,
      endIso,
      isLive: false,
    });
  }

  async function handleApplyFleetSetpoint() {
    const trimmedValue = fleetSetpointInput.trim();
    if (trimmedValue.length === 0) {
      setFleetSetpointActionError("Inserisci un valore percentuale tra 0 e 100.");
      return;
    }

    const numericValue = Number(trimmedValue);
    if (!Number.isFinite(numericValue) || numericValue < 0 || numericValue > 100) {
      setFleetSetpointActionError("Inserisci un valore percentuale valido tra 0 e 100.");
      return;
    }

    setFleetSetpointActionBusy(true);
    setFleetSetpointActionError(null);
    try {
      const nextFleetControl = await setFleetControlSetpoint({ value: numericValue });
      if (!isMountedRef.current) {
        return;
      }
      setFleetControl(nextFleetControl);
      setFleetSetpointInputDirty(false);
      void refreshFleetControlStatus();
      void loadDashboardData(false);
    } catch (actionError) {
      if (!isMountedRef.current) {
        return;
      }
      setFleetSetpointActionError(
        actionError instanceof Error
          ? actionError.message
          : "Impossibile applicare il setpoint di flotta.",
      );
    } finally {
      if (isMountedRef.current) {
        setFleetSetpointActionBusy(false);
      }
    }
  }

  async function handleClearFleetSetpoint() {
    setFleetSetpointActionBusy(true);
    setFleetSetpointActionError(null);
    try {
      const nextFleetControl = await clearFleetControlSetpoint();
      if (!isMountedRef.current) {
        return;
      }
      setFleetControl(nextFleetControl);
      setFleetSetpointInputDirty(false);
      void refreshFleetControlStatus();
      void loadDashboardData(false);
    } catch (actionError) {
      if (!isMountedRef.current) {
        return;
      }
      setFleetSetpointActionError(
        actionError instanceof Error
          ? actionError.message
          : "Impossibile azzerare il setpoint di flotta.",
      );
    } finally {
      if (isMountedRef.current) {
        setFleetSetpointActionBusy(false);
      }
    }
  }

  async function handleToggleCci() {
    if (fleetControl === null) {
      return;
    }

    const config = fleetControl.modbus_tcp_slave;
    setCciToggleBusy(true);
    setCciToggleError(null);
    try {
      const nextFleetControl = await updateModbusTcpSlaveConfig({
        enabled: config.enabled,
        cci_enabled: !config.cci_enabled,
        host: config.host,
        port: config.port,
        unit_id: config.unit_id,
        cci_readback_enabled: config.cci_readback_enabled,
        cci_readback_range_percent: config.cci_readback_range_percent,
        cci_readback_stable_seconds: config.cci_readback_stable_seconds,
        cci_readback_active_power_only: config.cci_readback_active_power_only,
      });
      if (!isMountedRef.current) {
        return;
      }
      setFleetControl(nextFleetControl);
      void refreshFleetControlStatus();
      void loadDashboardData(false);
    } catch (actionError) {
      if (!isMountedRef.current) {
        return;
      }
      setCciToggleError(
        actionError instanceof Error
          ? actionError.message
          : "Impossibile aggiornare lo stato del CCI.",
      );
    } finally {
      if (isMountedRef.current) {
        setCciToggleBusy(false);
      }
    }
  }

  function handleSlaveSettingsDraftChange(
    key: keyof ModbusSlaveSettingsDraft,
    value: string | boolean,
  ) {
    setSlaveSettingsError(null);
    setSlaveSettingsMessage(null);
    setSlaveSettingsDirty(true);
    setSlaveSettingsDraft((current) =>
      current === null
        ? current
        : (() => {
            const nextDraft: ModbusSlaveSettingsDraft = { ...current };
            if (key === "enabled") {
              nextDraft.enabled = Boolean(value);
            } else if (key === "host") {
              nextDraft.host = String(value);
          } else if (key === "port") {
            nextDraft.port = String(value);
          } else if (key === "unitId") {
            nextDraft.unitId = String(value);
          } else if (key === "cciReadbackEnabled") {
            nextDraft.cciReadbackEnabled = Boolean(value);
          } else if (key === "cciReadbackRangePercent") {
            nextDraft.cciReadbackRangePercent = String(value);
          } else if (key === "cciReadbackStableSeconds") {
            nextDraft.cciReadbackStableSeconds = String(value);
          } else {
            nextDraft.cciReadbackActivePowerOnly = Boolean(value);
          }
          return nextDraft;
        })(),
    );
  }

  function resetSlaveSettingsDraft() {
    const nextDraft = buildModbusSlaveSettingsDraft(fleetControl);
    setSlaveSettingsDraft(nextDraft);
    setSlaveSettingsDirty(false);
    setSlaveSettingsError(null);
    setSlaveSettingsMessage(null);
  }

  function handleHsmBridgeSettingsDraftChange(
    key: keyof HsmBridgeSettingsDraft,
    value: string | boolean,
  ) {
    setHsmBridgeSettingsError(null);
    setHsmBridgeSettingsMessage(null);
    setHsmBridgeSettingsDirty(true);
    setHsmBridgeSettingsDraft((current) =>
      current === null
        ? current
        : (() => {
            const nextDraft: HsmBridgeSettingsDraft = { ...current };
            switch (key) {
              case "enabled":
                nextDraft.enabled = Boolean(value);
                break;
              case "hsmPort":
                nextDraft.hsmPort = String(value);
                break;
              case "inverterPort":
                nextDraft.inverterPort = String(value);
                break;
              case "hsmBaudRate":
                nextDraft.hsmBaudRate = String(value);
                break;
              case "hsmParity":
                nextDraft.hsmParity = String(value) as HsmBridgeSettingsDraft["hsmParity"];
                break;
              case "hsmStopBits":
                nextDraft.hsmStopBits = String(value);
                break;
              case "hsmByteSize":
                nextDraft.hsmByteSize = String(value);
                break;
              case "frameGapMs":
                nextDraft.frameGapMs = String(value);
                break;
              case "forwardDelayMs":
                nextDraft.forwardDelayMs = String(value);
                break;
              default:
                nextDraft.ackTimeoutMs = String(value);
                break;
            }
            return nextDraft;
          })(),
    );
  }

  function resetHsmBridgeSettingsDraft() {
    const nextDraft = buildHsmBridgeSettingsDraft(fleetControl);
    setHsmBridgeSettingsDraft(nextDraft);
    setHsmBridgeSettingsDirty(false);
    setHsmBridgeSettingsError(null);
    setHsmBridgeSettingsMessage(null);
  }

  async function handleApplySlaveSettings() {
    if (fleetControl === null || slaveSettingsDraft === null) {
      return;
    }

    const normalizedHost = slaveSettingsDraft.host.trim() || "0.0.0.0";
    const normalizedPort = Number(slaveSettingsDraft.port);
    const normalizedUnitId = Number(slaveSettingsDraft.unitId);
    const normalizedCciReadbackRangePercent = Number(
      slaveSettingsDraft.cciReadbackRangePercent,
    );
    const normalizedCciReadbackStableSeconds = Number(
      slaveSettingsDraft.cciReadbackStableSeconds,
    );

    if (!Number.isInteger(normalizedPort) || normalizedPort < 1 || normalizedPort > 65535) {
      setSlaveSettingsError("Inserisci una porta slave valida tra 1 e 65535.");
      return;
    }
    if (!Number.isInteger(normalizedUnitId) || normalizedUnitId < 1 || normalizedUnitId > 247) {
      setSlaveSettingsError("Inserisci un ID unita valido tra 1 e 247.");
      return;
    }
    if (
      slaveSettingsDraft.cciReadbackEnabled &&
      (!Number.isFinite(normalizedCciReadbackRangePercent)
        || normalizedCciReadbackRangePercent < 0
        || normalizedCciReadbackRangePercent > 100)
    ) {
      setSlaveSettingsError("Inserisci un range Y valido tra 0 e 100%.");
      return;
    }
    if (
      slaveSettingsDraft.cciReadbackEnabled &&
      (!Number.isFinite(normalizedCciReadbackStableSeconds)
        || normalizedCciReadbackStableSeconds < 0.1
        || normalizedCciReadbackStableSeconds > 3600)
    ) {
      setSlaveSettingsError("Inserisci un tempo di stabilita valido tra 0.1 e 3600 secondi.");
      return;
    }

    setSlaveSettingsBusy(true);
    setSlaveSettingsError(null);
    setSlaveSettingsMessage(null);
    try {
      const nextFleetControl = await updateModbusTcpSlaveConfig({
        enabled: slaveSettingsDraft.enabled,
        cci_enabled: fleetControl.modbus_tcp_slave.cci_enabled,
        host: normalizedHost,
        port: normalizedPort,
        unit_id: normalizedUnitId,
        cci_readback_enabled: slaveSettingsDraft.cciReadbackEnabled,
        cci_readback_range_percent: normalizedCciReadbackRangePercent,
        cci_readback_stable_seconds: normalizedCciReadbackStableSeconds,
        cci_readback_active_power_only: slaveSettingsDraft.cciReadbackActivePowerOnly,
      });
      if (!isMountedRef.current) {
        return;
      }
      setFleetControl(nextFleetControl);
      setSlaveSettingsDraft(buildModbusSlaveSettingsDraft(nextFleetControl));
      setSlaveSettingsDirty(false);
      setSlaveSettingsMessage("Configurazione slave aggiornata.");
      void loadDashboardData(false);
    } catch (actionError) {
      if (!isMountedRef.current) {
        return;
      }
      setSlaveSettingsError(
        actionError instanceof Error
          ? actionError.message
          : "Impossibile aggiornare la configurazione dello slave Modbus TCP.",
      );
    } finally {
      if (isMountedRef.current) {
        setSlaveSettingsBusy(false);
      }
    }
  }

  async function handleApplyHsmBridgeSettings() {
    if (fleetControl === null || hsmBridgeSettingsDraft === null) {
      return;
    }

    const normalizedHsmPort = hsmBridgeSettingsDraft.hsmPort.trim();
    const normalizedInverterPort = hsmBridgeSettingsDraft.inverterPort.trim();
    const normalizedHsmBaudRate = Number(hsmBridgeSettingsDraft.hsmBaudRate);
    const normalizedHsmStopBits = Number(hsmBridgeSettingsDraft.hsmStopBits);
    const normalizedHsmByteSize = Number(hsmBridgeSettingsDraft.hsmByteSize);
    const normalizedFrameGapMs = Number(hsmBridgeSettingsDraft.frameGapMs);
    const normalizedForwardDelayMs = Number(hsmBridgeSettingsDraft.forwardDelayMs);
    const normalizedAckTimeoutMs = Number(hsmBridgeSettingsDraft.ackTimeoutMs);

    if (hsmBridgeSettingsDraft.enabled && !normalizedHsmPort) {
      setHsmBridgeSettingsError("Seleziona la porta HSM.");
      return;
    }
    if (hsmBridgeSettingsDraft.enabled && !normalizedInverterPort) {
      setHsmBridgeSettingsError("Seleziona la porta inverter.");
      return;
    }
    if (normalizedHsmPort && normalizedHsmPort === normalizedInverterPort) {
      setHsmBridgeSettingsError("La porta HSM e la porta inverter devono essere diverse.");
      return;
    }
    if (!Number.isInteger(normalizedHsmBaudRate) || normalizedHsmBaudRate < 1) {
      setHsmBridgeSettingsError("Inserisci un baud rate HSM valido.");
      return;
    }
    if (!Number.isInteger(normalizedHsmStopBits) || ![1, 2].includes(normalizedHsmStopBits)) {
      setHsmBridgeSettingsError("I bit di stop HSM devono essere 1 o 2.");
      return;
    }
    if (
      !Number.isInteger(normalizedHsmByteSize) ||
      normalizedHsmByteSize < 5 ||
      normalizedHsmByteSize > 8
    ) {
      setHsmBridgeSettingsError("La dimensione byte HSM deve essere compresa tra 5 e 8.");
      return;
    }
    if (!Number.isInteger(normalizedFrameGapMs) || normalizedFrameGapMs < 5) {
      setHsmBridgeSettingsError("Il frame gap deve essere almeno 5 ms.");
      return;
    }
    if (!Number.isInteger(normalizedForwardDelayMs) || normalizedForwardDelayMs < 0) {
      setHsmBridgeSettingsError("Il ritardo inoltro deve essere un valore valido.");
      return;
    }
    if (!Number.isInteger(normalizedAckTimeoutMs) || normalizedAckTimeoutMs < 50) {
      setHsmBridgeSettingsError("Il timeout ACK deve essere almeno 50 ms.");
      return;
    }

    setHsmBridgeSettingsBusy(true);
    setHsmBridgeSettingsError(null);
    setHsmBridgeSettingsMessage(null);
    try {
      const nextFleetControl = await updateHsmBridgeConfig({
        enabled: hsmBridgeSettingsDraft.enabled,
        hsm_port: normalizedHsmPort,
        inverter_port: normalizedInverterPort,
        hsm_baud_rate: normalizedHsmBaudRate,
        hsm_parity: hsmBridgeSettingsDraft.hsmParity,
        hsm_stop_bits: normalizedHsmStopBits,
        hsm_byte_size: normalizedHsmByteSize,
        frame_gap_ms: normalizedFrameGapMs,
        forward_delay_ms: normalizedForwardDelayMs,
        ack_timeout_ms: normalizedAckTimeoutMs,
      });
      if (!isMountedRef.current) {
        return;
      }
      setFleetControl(nextFleetControl);
      setHsmBridgeSettingsDraft(buildHsmBridgeSettingsDraft(nextFleetControl));
      setHsmBridgeSettingsDirty(false);
      setHsmBridgeSettingsMessage("Configurazione bridge HSM aggiornata.");
    } catch (actionError) {
      if (!isMountedRef.current) {
        return;
      }
      setHsmBridgeSettingsError(
        actionError instanceof Error
          ? actionError.message
          : "Impossibile aggiornare la configurazione del bridge HSM.",
      );
    } finally {
      if (isMountedRef.current) {
        setHsmBridgeSettingsBusy(false);
      }
    }
  }

  async function executeDeleteAllDevices() {
    if (devices.length === 0 || deleteAllDevicesBusy) {
      return;
    }

    setDeleteAllDevicesBusy(true);
    try {
      await deleteAllDevices();
      if (!isMountedRef.current) {
        return;
      }
      setSelectedDeviceId(null);
      setSettingsDeviceId(null);
      setDevicePowerMap({});
      setDeviceOverviewMap({});
      setDevices([]);
      await loadDashboardData(false);
    } catch (actionError) {
      if (!isMountedRef.current) {
        return;
      }
      setNoticeDialog({
        title: "Rimozione non completata",
        message:
          actionError instanceof Error
            ? actionError.message
            : "Impossibile rimuovere tutti i dispositivi.",
        tone: "error",
      });
    } finally {
      if (isMountedRef.current) {
        setDeleteAllDevicesBusy(false);
      }
    }
  }

  async function executeDeleteSingleDevice(device: Device) {
    if (deleteDeviceBusyId !== null || deleteAllDevicesBusy) {
      return;
    }

    setDeleteDeviceBusyId(device.device_id);
    try {
      await deleteDevice(device.device_id);
      if (!isMountedRef.current) {
        return;
      }
      if (selectedDeviceId === device.device_id) {
        setSelectedDeviceId(null);
      }
      if (settingsDeviceId === device.device_id) {
        setSettingsDeviceId(null);
      }
      setDevices((currentDevices) =>
        currentDevices.filter((currentDevice) => currentDevice.device_id !== device.device_id),
      );
      setDevicePowerMap((currentMap) => {
        const nextMap = { ...currentMap };
        delete nextMap[device.device_id];
        return nextMap;
      });
      setDeviceOverviewMap((currentMap) => {
        const nextMap = { ...currentMap };
        delete nextMap[device.device_id];
        return nextMap;
      });
      await loadDashboardData(false);
    } catch (actionError) {
      if (!isMountedRef.current) {
        return;
      }
      setNoticeDialog({
        title: "Rimozione non completata",
        message:
          actionError instanceof Error
            ? actionError.message
            : "Impossibile rimuovere il dispositivo.",
        tone: "error",
      });
    } finally {
      if (isMountedRef.current) {
        setDeleteDeviceBusyId(null);
      }
    }
  }

  function handleDeleteAllDevices() {
    if (devices.length === 0 || deleteAllDevicesBusy) {
      return;
    }
    setDeleteDialog({
      kind: "bulk",
      count: devices.length,
      stage: "initial",
    });
  }

  function handleDeleteSingleDevice(device: Device) {
    if (deleteDeviceBusyId !== null || deleteAllDevicesBusy) {
      return;
    }
    setDeleteDialog({
      kind: "single",
      device,
    });
  }

  function handleDeleteDialogClose() {
    if (deleteAllDevicesBusy || deleteDeviceBusyId !== null) {
      return;
    }
    setDeleteDialog(null);
  }

  function handleDeleteDialogConfirm() {
    if (deleteDialog === null) {
      return;
    }
    if (deleteDialog.kind === "bulk" && deleteDialog.stage === "initial") {
      setDeleteDialog({
        ...deleteDialog,
        stage: "final",
      });
      return;
    }

    const pendingAction = deleteDialog;
    setDeleteDialog(null);
    if (pendingAction.kind === "single") {
      void executeDeleteSingleDevice(pendingAction.device);
      return;
    }
    void executeDeleteAllDevices();
  }

  async function handleApplyDeviceSetpoint() {
    if (selectedDevice === null) {
      return;
    }

    const trimmedValue = deviceSetpointInput.trim();
    if (trimmedValue.length === 0) {
      setDeviceSetpointActionError("Inserisci un valore percentuale tra 0 e 100.");
      return;
    }

    const numericValue = Number(trimmedValue);
    if (!Number.isFinite(numericValue) || numericValue < 0 || numericValue > 100) {
      setDeviceSetpointActionError("Inserisci un valore percentuale valido tra 0 e 100.");
      return;
    }

    setDeviceSetpointActionBusy(true);
    setDeviceSetpointActionError(null);
    setDeviceSetpointActionMessage(null);
    try {
      const response = await sendActivePowerLimit(selectedDevice.device_id, { value: numericValue });
      if (!isMountedRef.current) {
        return;
      }
      setDeviceSetpointActionMessage(response.message || "Setpoint inviato.");
      void loadDashboardData(false);
    } catch (actionError) {
      if (!isMountedRef.current) {
        return;
      }
      setDeviceSetpointActionError(
        actionError instanceof Error
          ? actionError.message
          : "Impossibile inviare il setpoint inverter.",
      );
    } finally {
      if (isMountedRef.current) {
        setDeviceSetpointActionBusy(false);
      }
    }
  }

  const loadSerialPortOptions = useCallback(async () => {
    try {
      const result = await getSerialPorts();
      if (!isMountedRef.current) {
        return;
      }
      setSerialPorts(result.ports);
    } catch {
      if (!isMountedRef.current) {
        return;
      }
      setSerialPorts([]);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    void loadDashboardData();
    void refreshFleetControlStatus();

    const intervalId = window.setInterval(() => {
      void loadDashboardData(false);
    }, DASHBOARD_LIVE_REFRESH_MS);

    const fleetIntervalId = window.setInterval(() => {
      void refreshFleetControlStatus();
    }, FLEET_CONTROL_FAST_REFRESH_MS);

    return () => {
      isMountedRef.current = false;
      window.clearInterval(intervalId);
      window.clearInterval(fleetIntervalId);
    };
  }, [refreshFleetControlStatus]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setFooterTime(new Date());
    }, 1000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    if (slaveSettingsDirty) {
      return;
    }
    setSlaveSettingsDraft(buildModbusSlaveSettingsDraft(fleetControl));
  }, [fleetControl, slaveSettingsDirty]);

  useEffect(() => {
    if (hsmBridgeSettingsDirty) {
      return;
    }
    setHsmBridgeSettingsDraft(buildHsmBridgeSettingsDraft(fleetControl));
  }, [fleetControl, hsmBridgeSettingsDirty]);

  useEffect(() => {
    if (!isOperatorComSettingsOpen) {
      return;
    }
    void loadSerialPortOptions();
  }, [isOperatorComSettingsOpen, loadSerialPortOptions]);

  useEffect(() => {
    if (!isOperatorSettingsPageOpen && isOperatorComSettingsOpen) {
      setIsOperatorComSettingsOpen(false);
    }
  }, [isOperatorComSettingsOpen, isOperatorSettingsPageOpen]);

  useEffect(() => {
    if (!isOperatorSettingsPageOpen && isOperatorControlAuditPageOpen) {
      setIsOperatorControlAuditPageOpen(false);
    }
  }, [isOperatorControlAuditPageOpen, isOperatorSettingsPageOpen]);

  useEffect(() => {
    if (dashboardMode !== "operator" && isOperatorComSettingsOpen) {
      setIsOperatorComSettingsOpen(false);
    }
  }, [dashboardMode, isOperatorComSettingsOpen]);

  useEffect(() => {
    if (networkPendingChange === null) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshNetworkPendingChange();
    }, 1000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [networkPendingChange]);

  useEffect(() => {
    function handleResize() {
      setViewportWidth(window.innerWidth);
    }

    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(DASHBOARD_MODE_STORAGE_KEY, dashboardMode);
  }, [dashboardMode]);

  useEffect(() => {
    if (fleetSetpointInputDirty) {
      return;
    }
    setFleetSetpointInput(
      fleetControl?.active_power_limit_percent != null
        ? String(Math.round(fleetControl.active_power_limit_percent))
        : "",
    );
  }, [fleetControl?.active_power_limit_percent, fleetSetpointInputDirty]);

  const summaryItems = buildSummaryItems(summary, loading, error !== null);
  const availability =
    summary && summary.total_devices > 0
      ? Math.round((summary.online_devices / summary.total_devices) * 100)
      : 0;
  const selectedDevice =
    devices.find((device) => device.device_id === selectedDeviceId) ?? null;
  const selectedOverview =
    selectedDevice !== null ? deviceOverviewMap[selectedDevice.device_id] ?? null : null;
  const liteDevicePowerCommand =
    selectedOverview?.commands.find((command) => command.key === "active_power_limit") ?? null;
  const settingsDevice =
    devices.find((device) => device.device_id === settingsDeviceId) ?? null;
  const referenceDevice = getReferenceDevice(devices, deviceOverviewMap, devicePowerMap);
  const sceneDevice = selectedDevice ?? referenceDevice?.device ?? null;
  const sceneOverview = selectedOverview ?? referenceDevice?.overview ?? null;
  const activeGroups = selectedDevice
    ? buildDeviceGroups(selectedDevice, selectedOverview)
    : buildFleetGroups(summary, referenceDevice?.overview ?? null);
  const fleetChartSeries = buildFleetChartSeries(powerHistory);
  const liteFleetChartSeries = buildLiteFleetChartSeries(powerHistory);
  const liteSelectedSummaryItems =
    selectedDevice !== null
      ? buildLiteSelectedSummaryItems(selectedDevice, selectedOverview)
      : [];
  const railSummaryItems =
    selectedDevice !== null
      ? buildSelectedSummaryItems(selectedDevice, selectedOverview)
      : summaryItems.slice(0, 4);
  const liveFocusItems = buildLiveFocusItems(
    devices,
    devicePowerMap,
    selectedDevice,
    selectedOverview,
  );
  const sceneDcSignals = pickTelemetrySignals(sceneOverview, DC_SIGNAL_DEFINITIONS);
  const sceneAcSignals = pickTelemetrySignals(sceneOverview, AC_SIGNAL_DEFINITIONS);
  const sceneStatus = selectedDevice
    ? selectedDevice.status
    : referenceDevice?.device.status ??
      (summary && summary.online_devices > 0 ? "online" : devices.length > 0 ? "pending" : "offline");
  const sceneTitle = selectedDevice ? selectedDevice.name : "Panoramica impianto";
  const sceneCaption =
    selectedDevice && selectedOverview
      ? `${selectedDevice.brand} | ${selectedDevice.model}`
      : sceneDevice && sceneOverview
        ? `Riferimento live: ${sceneDevice.name} | ${sceneDevice.brand} | ${sceneDevice.model}`
        : "Nessun riferimento live disponibile. La scena si popolerà con il primo overview valido.";
  const scenePowerValue = selectedOverview
    ? `${metricFormatter.format(selectedOverview.metrics.power_kw)} kW`
    : summary
      ? `${metricFormatter.format(summary.total_power_kw)} kW`
      : "--";
  const scenePowerNote = selectedOverview
    ? "Potenza attiva disponibile sull'ultimo polling utile."
    : "Aggregato impianto con riferimento live contestuale.";
  const availabilityRatio =
    summary && summary.total_devices > 0
      ? `${summary.online_devices}/${summary.total_devices} online`
      : devices.length > 0
        ? `0/${devices.length} online`
        : "--/-- online";
  const fleetSetpointValue = formatFleetSetpointValue(fleetControl);
  const fleetSetpointNote = buildFleetSetpointNote(fleetControl);
  const fleetSetpointCaption = buildFleetSetpointCaption(fleetControl);
  const fleetSetpointConfigLabel = buildFleetSetpointConfigLabel(fleetControl);
  const plantPowerComparison = buildPlantPowerComparison(summary);
  const plantPowerProgressWidth =
    plantPowerComparison.utilizationPercent == null
      ? 0
      : Math.max(0, Math.min(plantPowerComparison.utilizationPercent, 100));
  const systemHealthRuntimeIssueCount = countHealthRuntimeIssues(systemHealth);
  const systemHealthHasAttention =
    systemHealth !== null &&
    (
      !systemHealth.polling.running ||
      systemHealth.status_counts.offline > 0 ||
      systemHealth.status_counts.warning > 0 ||
      systemHealth.status_counts.fault > 0 ||
      systemHealthRuntimeIssueCount > 0 ||
      systemHealth.modbus_tcp_slave.startup_error !== null
    );
  const fleetReadinessHasAttention =
    fleetControl?.readiness.overall_state === "warn" ||
    fleetControl?.readiness.overall_state === "fail";
  const timelineHasAttention =
    fleetControl?.timeline_events.some(
      (event) => event.level === "warning" || event.level === "error",
    ) ?? false;
  const operatorDashboardHasAttention =
    systemHealthHasAttention || fleetReadinessHasAttention || timelineHasAttention;
  const systemHealthSummary = buildSystemHealthSummary(
    systemHealth,
    loading,
    systemHealthError,
  );
  const liteHeroMessage = buildLiteHeroMessage(
    summary,
    loading,
    error !== null,
    systemHealthHasAttention,
  );
  const sceneMetrics =
    selectedDevice && selectedOverview
      ? [
          {
            label: "Energia oggi",
            value: `${metricFormatter.format(selectedOverview.metrics.daily_energy_kwh)} kWh`,
            note: "Yield giornaliero disponibile",
          },
          {
            label: "Energia totale",
            value: `${metricFormatter.format(selectedOverview.metrics.total_energy_kwh)} kWh`,
            note: "Contatore cumulato del dispositivo",
          },
          {
            label: "Temperatura",
            value: `${metricFormatter.format(selectedOverview.metrics.temperature_c)} C`,
            note: "Lettura termica corrente",
          },
          {
            label: "Diagnostica",
            value: `${selectedOverview.diagnostics.response_time_ms} ms`,
            note: selectedOverview.diagnostics.last_error ?? "Ultimo polling senza errori.",
          },
        ]
      : [
          {
            label: "Dispositivi online",
            value: summary ? integerFormatter.format(summary.online_devices) : "--",
            note: "Asset con telemetria live attiva",
          },
          {
            label: "Dispositivi offline",
            value: summary ? integerFormatter.format(summary.offline_devices) : "--",
            note: "Asset da verificare o in attesa",
          },
          {
            label: "Energia oggi",
            value: summary ? `${metricFormatter.format(summary.daily_energy_kwh)} kWh` : "--",
            note: "Produzione cumulata di giornata",
          },
          {
            label: "Energia totale",
            value: summary ? `${metricFormatter.format(summary.total_energy_kwh)} kWh` : "--",
            note: "Produzione complessiva dell'impianto",
          },
        ];
  const isCompactSidebarLayout = viewportWidth <= 1120;
  const isMobileLayout = viewportWidth <= 900;
  const liteDevices = devices
    .slice()
    .sort((left, right) => {
      const priorityDelta =
        getLiteDevicePriority(left.status) - getLiteDevicePriority(right.status);
      if (priorityDelta !== 0) {
        return priorityDelta;
      }

      const powerDelta =
        (devicePowerMap[right.device_id] ?? Number.NEGATIVE_INFINITY) -
        (devicePowerMap[left.device_id] ?? Number.NEGATIVE_INFINITY);
      if (powerDelta !== 0) {
        return powerDelta;
      }

      return left.name.localeCompare(right.name, "it");
    });
  const stageTabs: StageTabOption[] = selectedDevice
    ? [
        { key: "live", label: "Live" },
        { key: "history", label: "Storico" },
        { key: "commands", label: "Comandi" },
      ]
    : [
        { key: "live", label: "Live" },
        { key: "history", label: "Storico" },
      ];
  const activeMobileStageTab = stageTabs.some((tab) => tab.key === mobileStageTab)
    ? mobileStageTab
    : stageTabs[0].key;
  function openOperatorPlantView() {
    setSelectedDeviceId(null);
    setIsOperatorSettingsPageOpen(false);
    setIsOperatorControlAuditPageOpen(false);
    setIsOperatorComSettingsOpen(false);
    setIsOperatorProvisioningOpen(false);
    setIsFleetDrawerOpen(false);
    setIsFocusPanelOpen(false);
    setMobileStageTab("live");
  }

  const discoveryActive = isDiscoveryRunning || operatorScanBusy;
  const singleDeleteDialog = deleteDialog?.kind === "single" ? deleteDialog : null;
  const bulkDeleteDialog = deleteDialog?.kind === "bulk" ? deleteDialog : null;
  const deleteDialogBusy =
    singleDeleteDialog !== null
      ? deleteDeviceBusyId === singleDeleteDialog.device.device_id
      : bulkDeleteDialog !== null
        ? deleteAllDevicesBusy
        : false;
  const deleteDialogTitle = singleDeleteDialog
    ? "Rimuovere dispositivo?"
    : bulkDeleteDialog?.stage === "final"
      ? "Conferma definitiva"
      : "Rimuovere tutto il parco inverter?";
  const deleteDialogMessage = singleDeleteDialog
    ? `Il dispositivo "${singleDeleteDialog.device.name}" verra rimosso dal parco inverter configurato insieme a storico potenza e ultimi setpoint salvati.`
    : bulkDeleteDialog?.stage === "final"
      ? `Conferma definitiva: verranno rimossi tutti i ${bulkDeleteDialog?.count ?? 0} dispositivi configurati. L'operazione e irreversibile.`
      : `Verranno rimossi tutti i ${bulkDeleteDialog?.count ?? 0} dispositivi configurati, insieme a storico potenza e ultimi setpoint salvati.`;
  const deleteDialogConfirmLabel =
    singleDeleteDialog !== null
      ? deleteDialogBusy
        ? "Eliminazione..."
        : "Conferma eliminazione"
      : bulkDeleteDialog?.stage === "final"
        ? deleteDialogBusy
          ? "Rimozione..."
          : "Conferma eliminazione"
        : "Continua";

  const sidebarContent = (
    <FleetSidebarContent
      summary={summary}
      loading={loading}
      error={error}
      availability={availability}
      devices={devices}
      selectedDeviceId={selectedDeviceId}
      devicePowerMap={devicePowerMap}
      deviceOverviewMap={deviceOverviewMap}
      onAddDevice={openManualAddDevice}
      onOpenDiscovery={openDiscoveryModal}
      onSelectFleet={() => {
        setSelectedDeviceId(null);
        setIsFleetDrawerOpen(false);
        setMobileStageTab("live");
      }}
      onSelectDevice={(deviceId) => {
        setSelectedDeviceId(deviceId);
        setIsFleetDrawerOpen(false);
        setMobileStageTab("live");
      }}
      onOpenSettings={(deviceId) => {
        setSettingsDeviceId(deviceId);
        setIsFleetDrawerOpen(false);
      }}
      discoveryActive={discoveryActive}
      discoveryResultCount={discoveryResultCount}
      viewMode={dashboardMode}
    />
  );

  useEffect(() => {
    setMobileStageTab("live");
    setIsFocusPanelOpen(false);
    setDeviceSetpointInput("");
    setDeviceSetpointActionError(null);
    setDeviceSetpointActionMessage(null);
    setDeviceSetpointActionBusy(false);
    setIsOperatorProvisioningOpen(false);
  }, [selectedDeviceId]);

  useEffect(() => {
    if (selectedDeviceId === null) {
      return;
    }

    const currentDeviceId = selectedDeviceId;
    let cancelled = false;
    let requestInFlight = false;

    async function refreshSelectedDeviceOverview() {
      if (requestInFlight) {
        return;
      }
      requestInFlight = true;
      try {
        const overview = await getDeviceOverview(currentDeviceId, { refresh: true });
        if (!isMountedRef.current || cancelled) {
          return;
        }

        setDeviceOverviewMap((current) => ({
          ...current,
          [currentDeviceId]: overview,
        }));
        setDevicePowerMap((current) => ({
          ...current,
          [currentDeviceId]: overview.metrics.power_kw,
        }));
      } catch {
        // Keep the cached or stub overview already visible in the scene.
      } finally {
        requestInFlight = false;
      }
    }

    void refreshSelectedDeviceOverview();
    const intervalId = window.setInterval(() => {
      void refreshSelectedDeviceOverview();
    }, SELECTED_DEVICE_REFRESH_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [selectedDeviceId]);

  useEffect(() => {
    if (!isCompactSidebarLayout) {
      setIsFleetDrawerOpen(false);
    }
  }, [isCompactSidebarLayout]);

  useEffect(() => {
    setIsFocusPanelOpen(false);
    if (dashboardMode === "lite") {
      setIsFleetDrawerOpen(false);
    }
    if (dashboardMode !== "operator") {
      setIsOperatorProvisioningOpen(false);
      setIsOperatorSettingsPageOpen(false);
      setIsOperatorControlAuditPageOpen(false);
    }
  }, [dashboardMode]);

  const isOperatorMode = dashboardMode === "operator";
  const isDesktopLiteSidebarMode = dashboardMode === "lite" && !isCompactSidebarLayout;
  const showDesktopLiteSidebarToggle = isDesktopLiteSidebarMode;
  const operatorDevices = filterAndSortOperatorDevices(
    devices,
    devicePowerMap,
    "",
    "all",
    "status",
  );
  const operatorOverview = selectedOverview ?? referenceDevice?.overview ?? null;
  const operatorPrimaryStatus = selectedDevice?.status ?? sceneStatus;
  const operatorPrimaryTitle = selectedDevice ? selectedDevice.name : "Sala operatore";
  const operatorPrimaryCaption = selectedDevice
    ? `${selectedDevice.brand} | ${selectedDevice.model}`
    : summary
      ? `${summary.online_devices}/${summary.total_devices} inverter disponibili`
      : "Monitoraggio pronto";
  const operatorPrimaryLastValid = formatRuntimeTimestamp(
    operatorOverview?.diagnostics.last_valid_data_at,
  );
  const operatorPrimaryLastContact = formatRuntimeTimestamp(
    operatorOverview?.diagnostics.last_contact_at,
  );
  const operatorCosPhiPoint = findCompactTelemetryPoint(operatorOverview, OPERATOR_COSPHI_LOOKUP);
  const operatorTemperaturePoint = findCompactTelemetryPoint(
    operatorOverview,
    OPERATOR_TEMPERATURE_LOOKUP,
  );
  const operatorTotalEnergyPoint = findCompactTelemetryPoint(
    operatorOverview,
    OPERATOR_TOTAL_ENERGY_LOOKUP,
  );
  const operatorSceneMetrics = [
    ...(selectedDevice
      ? [
          {
            label: "Cosphi",
            value: formatCompactTelemetryPoint(operatorCosPhiPoint),
            note:
              operatorCosPhiPoint !== null
                ? translateTelemetryLabel(operatorCosPhiPoint.label)
                : "Dato non esposto dal profilo attivo",
          },
          {
            label: "Temperatura",
            value: formatCompactTelemetryPoint(operatorTemperaturePoint),
            note:
              operatorTemperaturePoint !== null
                ? translateTelemetryLabel(operatorTemperaturePoint.label)
                : "Lettura termica non disponibile",
          },
          {
            label: "Energia totale",
            value: formatCompactTelemetryPoint(operatorTotalEnergyPoint),
            note:
              operatorTotalEnergyPoint !== null
                ? translateTelemetryLabel(operatorTotalEnergyPoint.label)
                : "Contatore cumulato non disponibile",
          },
          {
            label: "Ultimo dato valido",
            value: operatorPrimaryLastValid ?? "in attesa",
            note: "Timestamp dell'ultima telemetria completa ricevuta",
          },
        ]
      : [
          {
            label: "Stato",
            value: translateStatusLabel(operatorPrimaryStatus),
            note: systemHealthSummary,
          },
          {
            label: "Ultimo dato valido",
            value: operatorPrimaryLastValid ?? "in attesa",
            note: "Ultima telemetria completa utile per la vista operatore",
          },
          {
            label: "Ultimo contatto",
            value: operatorPrimaryLastContact ?? "non disponibile",
            note: "Contatto piu recente sul riferimento live di impianto",
          },
          {
            label: "Setpoint esterno",
            value: fleetSetpointValue,
            note: fleetSetpointNote,
          },
        ]),
  ];
  const operatorSidebarContent = (
    <OperatorDeviceGridPanel
      summary={summary}
      loading={loading}
      error={error}
      availabilityRatio={availabilityRatio}
      selectedDeviceId={selectedDeviceId}
      pageDevices={operatorDevices}
      totalDevices={devices.length}
      devicePowerMap={devicePowerMap}
      deviceOverviewMap={deviceOverviewMap}
      settingsActive={isOperatorSettingsPageOpen}
      deleteDeviceBusyId={deleteDeviceBusyId}
      onSelectFleet={openOperatorPlantView}
      onSelectDevice={(deviceId) => {
        setSelectedDeviceId(deviceId);
        setIsOperatorSettingsPageOpen(false);
        setIsOperatorControlAuditPageOpen(false);
        setIsOperatorComSettingsOpen(false);
        setIsOperatorProvisioningOpen(false);
        setIsFleetDrawerOpen(false);
      }}
      onOpenSettingsPage={() => {
        setSelectedDeviceId(null);
        setIsOperatorSettingsPageOpen(true);
        setIsOperatorControlAuditPageOpen(false);
        setIsFleetDrawerOpen(false);
      }}
      onOpenProvisioning={() => {
        setIsOperatorSettingsPageOpen(false);
        setIsOperatorControlAuditPageOpen(false);
        setIsOperatorProvisioningOpen(true);
        setIsFleetDrawerOpen(false);
      }}
      onEditDevice={(device) => {
        setSettingsDeviceId(device.device_id);
        setIsFleetDrawerOpen(false);
      }}
      onDeleteDevice={(device) => {
        void handleDeleteSingleDevice(device);
      }}
    />
  );

  return (
    <>
      <SolarAmbientBackground enabled={solarBackgroundEnabled} />
      <div className="app-shell">
      <div
        className={`control-room ${dashboardMode === "lite" ? "control-room--lite" : ""} ${
          isOperatorMode ? "control-room--operator" : ""
        } ${
          isOperatorMode ? "control-room--operator-dark" : ""
        } ${
          solarBackgroundEnabled ? "control-room--solar-ambient" : ""
        } ${
          showDesktopLiteSidebarToggle ? "control-room--lite-toggle-ready" : ""
        } ${
          isDesktopLiteSidebarMode && !isLiteSidebarExpanded ? "control-room--lite-collapsed" : ""
        }`}
      >
        {showDesktopLiteSidebarToggle ? (
          <button
            className="secondary-button control-room-sidebar-toggle"
            type="button"
            onClick={() => setIsLiteSidebarExpanded((current) => !current)}
            aria-label={isLiteSidebarExpanded ? "Nascondi dispositivi" : "Mostra dispositivi"}
            title={isLiteSidebarExpanded ? "Nascondi dispositivi" : "Mostra dispositivi"}
          >
            {isLiteSidebarExpanded ? "<<" : ">>"}
          </button>
        ) : null}
        {isOperatorMode && !isCompactSidebarLayout ? (
          <aside className="control-sidebar control-sidebar--operator">{operatorSidebarContent}</aside>
        ) : isDesktopLiteSidebarMode ? (
          <div className="control-sidebar-slot" aria-hidden={!isLiteSidebarExpanded}>
            <aside className="control-sidebar control-sidebar--lite-inline">{sidebarContent}</aside>
          </div>
        ) : !isCompactSidebarLayout ? (
          <aside className="control-sidebar">{sidebarContent}</aside>
        ) : null}

        <div className="control-stage">
          {networkPendingChange ? (
            <NetworkPendingChangeAlert
              pendingChange={networkPendingChange}
              busyAction={networkPendingActionBusy}
              error={networkPendingActionError}
              onConfirm={() => void handleConfirmNetworkChange()}
              onRollback={() => void handleRollbackNetworkChange()}
            />
          ) : null}

          {operatorProvisioningProgress ? (
            <OperatorProvisioningPageAlert
              progress={operatorProvisioningProgress}
              busy={operatorProvisioningBusy}
              onCancel={() => {
                setOperatorProvisioningCancelRequestToken((current) => current + 1);
              }}
              onDismiss={() => setOperatorProvisioningProgress(null)}
            />
          ) : null}

          {firstConnectWatch ? (
            <OperatorFirstConnectAlert
              watch={firstConnectWatch}
              devices={devices}
              overviewMap={deviceOverviewMap}
              onDismiss={() => setFirstConnectWatch(null)}
            />
          ) : null}

          <header className="control-header">
            {dashboardMode !== "operator" ? (
              <div className="control-title-wrap">
                <p className="control-overline">Sala controllo fotovoltaica</p>
                <h1>PV Edge Manager</h1>
                <p className="control-copy">
                  {dashboardMode === "pro"
                    ? "Supervisione professionale di impianto con potenza, disponibilita, storico e stato operativo sempre leggibili nella vista generale."
                    : "Vista semplificata per operatori con pochi KPI chiari, trend di produzione e stato sintetico degli inverter."}
                </p>
                <div className="control-title-actions">
                  <DashboardModeSwitch mode={dashboardMode} onChange={setDashboardMode} />
                  {dashboardMode === "pro" ? (
                    <button
                      className="secondary-button control-title-action button-with-icon"
                      type="button"
                      onClick={() => setIsSystemSettingsOpen(true)}
                    >
                      <LanIcon />
                      <span>LAN Settings</span>
                    </button>
                  ) : null}
                  <button
                    className={`secondary-button control-title-action ${
                      systemHealthHasAttention ? "control-title-action--attention" : ""
                    }`}
                    type="button"
                    onClick={() => setIsSystemHealthOpen(true)}
                  >
                    Health sistema
                  </button>
                  {dashboardMode === "pro" ? (
                    <button
                      className="danger-outline-button control-title-action"
                      type="button"
                      onClick={() => void handleDeleteAllDevices()}
                      disabled={devices.length === 0 || deleteAllDevicesBusy}
                      title="Rimuovi tutti i dispositivi configurati"
                    >
                      {deleteAllDevicesBusy ? "Rimozione..." : "Rimuovi tutti"}
                    </button>
                  ) : null}
                  <span className="control-title-action-note">{systemHealthSummary}</span>
                </div>
              </div>
            ) : null}
            <div className="control-header-actions">
              {isCompactSidebarLayout ? (
                <div className="control-mobile-actions">
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => setIsFleetDrawerOpen(true)}
                  >
                    {isOperatorMode ? "Inverter" : "Dispositivi"}
                  </button>
                  {dashboardMode === "operator" ? (
                    <button
                      className={`secondary-button ${
                        operatorDashboardHasAttention ? "secondary-button--attention" : ""
                      }`}
                      type="button"
                      onClick={() => {
                        setSelectedDeviceId(null);
                        setIsOperatorSettingsPageOpen(true);
                        setIsOperatorControlAuditPageOpen(false);
                        setIsFleetDrawerOpen(false);
                      }}
                    >
                      Impostazioni
                    </button>
                  ) : dashboardMode === "pro" ? (
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={openDiscoveryModal}
                    >
                      Browsing
                      {discoveryResultCount > 0 ? (
                        <span className="button-counter-badge">{discoveryResultCount}</span>
                      ) : null}
                    </button>
                  ) : null}
                  {dashboardMode !== "operator" ? (
                    <button
                      className={`secondary-button ${
                        systemHealthHasAttention ? "secondary-button--attention" : ""
                      }`}
                      type="button"
                      onClick={() => setIsSystemHealthOpen(true)}
                    >
                      Health
                    </button>
                  ) : null}
                  {dashboardMode === "pro" ? (
                    <button
                      className="secondary-button button-with-icon"
                      type="button"
                      onClick={() => setIsSystemSettingsOpen(true)}
                    >
                      <LanIcon />
                      <span>LAN Settings</span>
                    </button>
                  ) : null}
                  {dashboardMode === "pro" ? (
                    <button
                      className={`action-button ${discoveryActive ? "action-button--busy" : ""}`}
                      type="button"
                      onClick={openManualAddDevice}
                    >
                      Aggiungi
                      {discoveryActive ? (
                        <span className="button-activity-dot" aria-hidden="true" />
                      ) : null}
                    </button>
                  ) : null}
                </div>
              ) : null}
              {dashboardMode === "pro" ? (
                <>
                  <div className="control-metric-chip">
                    <span>Disponibilita impianto</span>
                    <strong>
                      {loading ? "Sincronizzazione..." : error ? "--" : `${availability}%`}
                    </strong>
                    <p className="control-metric-chip-note">
                      {loading ? "Rilevazione dispositivi..." : error ? "--/-- online" : availabilityRatio}
                    </p>
                  </div>
                  <div className="control-metric-chip control-metric-chip--accent">
                    <span>Coda allarmi</span>
                    <strong>
                      {loading
                        ? "Caricamento..."
                        : error
                          ? "--"
                          : `${summary?.active_alarms ?? 0} attivi`}
                    </strong>
                    <p className="control-metric-chip-note">
                      {loading
                        ? "Allineamento diagnostica..."
                        : error
                          ? "Nessun dettaglio disponibile."
                          : (summary?.active_alarms ?? 0) > 0
                            ? "Richiede verifica operatore."
                            : "Nessun allarme attivo rilevato."}
                    </p>
                  </div>
                  <FleetSetpointSummaryCard
                    loading={loading}
                    fleetControl={fleetControl}
                    fleetSetpointValue={fleetSetpointValue}
                    fleetSetpointNote={fleetSetpointNote}
                    fleetSetpointConfigLabel={fleetSetpointConfigLabel}
                    fleetSetpointCaption={fleetSetpointCaption}
                    cciToggleBusy={cciToggleBusy}
                    cciToggleError={cciToggleError}
                    onToggleCci={() => void handleToggleCci()}
                  />
                  <div className="control-metric-chip control-metric-chip--primary">
                    <span>Potenza totale attuale</span>
                    <strong>
                      {summary ? formatCompactPowerKw(summary.total_power_kw) : "--"}
                    </strong>
                    <p className="control-metric-chip-note">
                      {loading
                        ? "Calcolo produzione live e confronto nominale..."
                        : error
                          ? "Produzione istantanea non disponibile."
                          : plantPowerComparison.comparison}
                    </p>
                    <div className="control-metric-progress" aria-hidden="true">
                      <span style={{ width: `${plantPowerProgressWidth}%` }} />
                    </div>
                    <p className="control-metric-chip-subnote">
                      {loading
                        ? "Attendo copertura nominale..."
                        : error
                          ? "Copertura nominale non disponibile."
                          : plantPowerComparison.utilizationPercent != null
                            ? `${metricFormatter.format(plantPowerComparison.utilizationPercent)}% della potenza nominale AC installata.`
                            : "Percentuale di utilizzo nominale non disponibile."}
                    </p>
                    <p className="control-metric-chip-subnote">
                      {loading ? "..." : error ? "..." : plantPowerComparison.coverage}
                    </p>
                  </div>
                </>
              ) : dashboardMode === "operator" ? (
                <>
                  {selectedDevice === null ? (
                    <OperatorPlantControlCard
                      loading={loading}
                      powerValue={summary ? formatCompactPowerKw(summary.total_power_kw) : "--"}
                      caption={
                        summary
                          ? `${summary.online_devices}/${summary.total_devices} inverter online`
                          : "Nessun dispositivo disponibile"
                      }
                      inputValue={fleetSetpointInput}
                      actionBusy={fleetSetpointActionBusy}
                      actionError={fleetSetpointActionError}
                      onInputChange={(value) => {
                        setFleetSetpointInput(value);
                        setFleetSetpointInputDirty(true);
                        setFleetSetpointActionError(null);
                      }}
                      onApply={() => void handleApplyFleetSetpoint()}
                      onClear={() => void handleClearFleetSetpoint()}
                    />
                  ) : (
                    <OperatorSummaryCard
                      label={operatorPrimaryTitle}
                      value={scenePowerValue}
                      note={operatorPrimaryCaption}
                      tone={getStatusTone(operatorPrimaryStatus)}
                    >
                      <div className="operator-summary-card__status-row">
                        <StatusBadge status={operatorPrimaryStatus} />
                        <span className="operator-summary-card__status-note">
                          {operatorPrimaryLastValid
                            ? `Ultimo dato utile ${operatorPrimaryLastValid}`
                            : "In attesa di telemetria completa"}
                        </span>
                      </div>
                    </OperatorSummaryCard>
                  )}
                  <OperatorSummaryCard
                    label="Setpoint esterno"
                    value={loading ? "Caricamento..." : fleetSetpointValue}
                    note={fleetSetpointConfigLabel}
                    tone={fleetControl?.active_power_limit_percent != null ? "warning" : "neutral"}
                    className="operator-summary-card--external-setpoint"
                  >
                    <div className="operator-summary-card__external-status">
                      <CciConnectionIndicator fleetControl={fleetControl} />
                      <CciControlToggle
                        fleetControl={fleetControl}
                        busy={cciToggleBusy}
                        error={cciToggleError}
                        onToggle={() => void handleToggleCci()}
                      />
                    </div>
                    <p className="operator-summary-card__support">
                      {fleetSetpointNote}
                      {" · "}
                      {fleetSetpointCaption}
                    </p>
                  </OperatorSummaryCard>
                </>
              ) : (
                <>
                  <div className="control-metric-chip control-metric-chip--primary">
                    <span>Potenza totale</span>
                    <strong>
                      {summary ? formatCompactPowerKw(summary.total_power_kw) : "--"}
                    </strong>
                    <p className="control-metric-chip-note">
                      {loading
                        ? "Aggiornamento produzione in corso..."
                        : error
                          ? "Produzione non disponibile."
                          : plantPowerComparison.comparison}
                    </p>
                  </div>
                  <div className="control-metric-chip">
                    <span>Disponibilita</span>
                    <strong>
                      {loading ? "Sincronizzazione..." : error ? "--" : `${availability}%`}
                    </strong>
                    <p className="control-metric-chip-note">
                      {loading ? "Rilevazione dispositivi..." : error ? "--/-- online" : availabilityRatio}
                    </p>
                  </div>
                  <div className="control-metric-chip control-metric-chip--accent">
                    <span>Allarmi</span>
                    <strong>
                      {loading
                        ? "Caricamento..."
                        : error
                          ? "--"
                          : `${summary?.active_alarms ?? 0} attivi`}
                    </strong>
                    <p className="control-metric-chip-note">
                      {loading
                        ? "Verifica stato impianto..."
                        : error
                          ? "Nessun dettaglio disponibile."
                          : (summary?.active_alarms ?? 0) > 0
                            ? "Richiede verifica operatore."
                            : "Nessun allarme attivo rilevato."}
                    </p>
                  </div>
                  <FleetSetpointSummaryCard
                    loading={loading}
                    fleetControl={fleetControl}
                    fleetSetpointValue={fleetSetpointValue}
                    fleetSetpointNote={fleetSetpointNote}
                    fleetSetpointConfigLabel={fleetSetpointConfigLabel}
                    fleetSetpointCaption={fleetSetpointCaption}
                    cciToggleBusy={cciToggleBusy}
                    cciToggleError={cciToggleError}
                    onToggleCci={() => void handleToggleCci()}
                  />
                </>
              )}
            </div>
          </header>

          {loading ? (
            <section className="panel-state" aria-live="polite">
              Caricamento dati in tempo reale dal backend...
            </section>
          ) : null}
          {error ? (
            <section className="panel-state panel-state--error" role="alert">
              Impossibile caricare i dati dal backend. {error}
            </section>
          ) : null}

          {isMobileLayout && dashboardMode === "pro" ? (
            <MobileStageTabs
              tabs={stageTabs}
              activeTab={activeMobileStageTab}
              onChange={setMobileStageTab}
            />
          ) : null}

          <div className="control-content">
            <main className="control-main">
              {dashboardMode === "operator" ? (
                <>
                  {isCompactSidebarLayout ? (
                    <section className="stage-panel operator-mobile-grid-panel">
                      {operatorSidebarContent}
                    </section>
                  ) : null}
                  {isOperatorSettingsPageOpen ? (
                    isOperatorControlAuditPageOpen ? (
                      <OperatorControlAuditPage
                        fleetControl={fleetControl}
                        health={systemHealth}
                        loading={loading}
                        error={error ?? systemHealthError}
                        onBackToSettings={() => setIsOperatorControlAuditPageOpen(false)}
                        onOpenPlant={openOperatorPlantView}
                        onOpenHealth={() => setIsSystemHealthOpen(true)}
                        onOpenHistory={() => setIsAdvancedFleetHistoryOpen(true)}
                      />
                    ) : (
                      <OperatorSettingsPage
                        deviceCount={devices.length}
                        systemHealthSummary={systemHealthSummary}
                        systemHealthHasAttention={systemHealthHasAttention}
                        fleetControl={fleetControl}
                        slaveSettingsDraft={slaveSettingsDraft}
                        slaveSettingsBusy={slaveSettingsBusy}
                        slaveSettingsDirty={slaveSettingsDirty}
                        slaveSettingsError={slaveSettingsError}
                        slaveSettingsMessage={slaveSettingsMessage}
                        hsmBridgeSettingsDraft={hsmBridgeSettingsDraft}
                        hsmBridgeSettingsBusy={hsmBridgeSettingsBusy}
                        hsmBridgeSettingsDirty={hsmBridgeSettingsDirty}
                        hsmBridgeSettingsError={hsmBridgeSettingsError}
                        hsmBridgeSettingsMessage={hsmBridgeSettingsMessage}
                        serialPorts={serialPorts}
                        deleteAllDevicesBusy={deleteAllDevicesBusy}
                        solarBackgroundEnabled={solarBackgroundEnabled}
                        onSlaveSettingsChange={handleSlaveSettingsDraftChange}
                        onApplySlaveSettings={() => void handleApplySlaveSettings()}
                        onResetSlaveSettings={resetSlaveSettingsDraft}
                        onHsmBridgeSettingsChange={handleHsmBridgeSettingsDraftChange}
                        onApplyHsmBridgeSettings={() => void handleApplyHsmBridgeSettings()}
                        onResetHsmBridgeSettings={resetHsmBridgeSettingsDraft}
                        onSolarBackgroundToggle={handleSolarBackgroundToggle}
                        onOpenProvisioning={() => {
                          setIsOperatorProvisioningOpen(true);
                        }}
                        onOpenComSettings={(section) => {
                          setOperatorComSettingsFocus(section);
                          setIsOperatorComSettingsOpen(true);
                        }}
                        onOpenLanSettings={() => {
                          setIsSystemSettingsOpen(true);
                        }}
                        onOpenHealth={() => {
                          setIsSystemHealthOpen(true);
                        }}
                        onOpenControlAudit={() => {
                          setIsOperatorControlAuditPageOpen(true);
                        }}
                        onOpenHistory={() => {
                          setIsAdvancedFleetHistoryOpen(true);
                        }}
                        onOpenPro={() => {
                          setDashboardMode("pro");
                        }}
                        onOpenPlant={openOperatorPlantView}
                        onDeleteAllDevices={() => void handleDeleteAllDevices()}
                      />
                    )
                  ) : selectedDevice ? (
                    <section className="stage-panel stage-panel--scene operator-scene-panel">
                      <InverterFlowScene
                        eyebrow="Inverter selezionato"
                        title={sceneTitle}
                        caption={sceneCaption}
                        status={operatorPrimaryStatus}
                        statusLabel={translateStatusLabel(operatorPrimaryStatus)}
                        powerLabel="Potenza attiva"
                        powerValue={scenePowerValue}
                        powerNote={scenePowerNote}
                        dcSignals={sceneDcSignals}
                        acSignals={sceneAcSignals}
                        metrics={operatorSceneMetrics}
                        canvasAction={
                          liteDevicePowerCommand ? (
                            <CompactDeviceSetpointControl
                              inputValue={deviceSetpointInput}
                              lastSetpointDisplay={liteDevicePowerCommand.last_set_display}
                              lastSetpointAt={liteDevicePowerCommand.last_set_at}
                              actionBusy={deviceSetpointActionBusy}
                              actionError={deviceSetpointActionError}
                              actionMessage={deviceSetpointActionMessage}
                              onInputChange={(value) => {
                                setDeviceSetpointInput(value);
                                setDeviceSetpointActionError(null);
                                setDeviceSetpointActionMessage(null);
                              }}
                              onApply={() => void handleApplyDeviceSetpoint()}
                            />
                          ) : null
                        }
                        headerAction={
                          <button
                            className="secondary-button inverter-scene-focus-button"
                            type="button"
                            onClick={openOperatorPlantView}
                          >
                            Torna all'impianto
                          </button>
                        }
                      />
                    </section>
                  ) : (
                    <div className="operator-plant-dashboard">
                      <section className="stage-panel stage-panel--history operator-plant-chart-panel">
                      <div className="stage-header">
                        <div>
                          <p className="panel-kicker">Vista impianto</p>
                          <h2>Potenza totale e inverter</h2>
                          <p className="stage-copy">
                            Trend live della produzione complessiva e delle singole macchine.
                          </p>
                        </div>
                        <span className="panel-meta">
                          {powerHistory?.device_series.length ?? 0} inverter tracciati
                        </span>
                      </div>
                      <PowerHistoryChart
                        labels={powerHistory?.labels ?? []}
                        series={fleetChartSeries}
                        loading={loading}
                        errorMessage={powerHistoryError}
                        emptyTitle="Storico potenza non ancora disponibile"
                        emptyMessage="La dashboard operatore mostrerà totale e singoli inverter non appena il backend avrà campioni reali di potenza."
                        {...OPERATOR_PLANT_CHART_EMPTY_STATE}
                        height={360}
                        rangePreset={powerHistoryRange.presetId}
                        rangeStart={powerHistoryRange.startIso}
                        rangeEnd={powerHistoryRange.endIso}
                        rangeIsLive={powerHistoryRange.isLive}
                        rangeMode={powerHistoryRange.mode}
                        onRangePresetChange={handlePowerHistoryRangePresetChange}
                        onRangeShift={handlePowerHistoryRangeShift}
                        onRangeJumpToLive={handlePowerHistoryJumpToLive}
                        onRangeCustomApply={handlePowerHistoryCustomRangeApply}
                      />
                      </section>
                      <div className="operator-plant-dashboard__grid">
                        <OperatorCommissioningReadinessPanel
                          fleetControl={fleetControl}
                          onOpenSettingsPage={() => {
                            setSelectedDeviceId(null);
                            setIsOperatorSettingsPageOpen(true);
                            setIsOperatorControlAuditPageOpen(false);
                            setIsOperatorComSettingsOpen(false);
                            setIsOperatorProvisioningOpen(false);
                          }}
                        />
                        <OperatorTimelinePanel
                          fleetControl={fleetControl}
                          onOpenHistory={() => {
                            setIsAdvancedFleetHistoryOpen(true);
                          }}
                        />
                      </div>
                    </div>
                  )}
                </>
              ) : dashboardMode === "lite" ? (
                selectedDevice ? (
                  <>
                    <section className="lite-summary-grid" aria-label="Indicatori dispositivo">
                      {liteSelectedSummaryItems.map((item) => (
                        <SummaryCard key={item.label} {...item} />
                      ))}
                    </section>

                    <section className="stage-panel stage-panel--scene">
                      <InverterFlowScene
                        eyebrow="Dettaglio dispositivo"
                        title={sceneTitle}
                        caption={sceneCaption}
                        status={sceneStatus}
                        statusLabel={translateStatusLabel(sceneStatus)}
                        powerLabel="Potenza dispositivo"
                        powerValue={scenePowerValue}
                        powerNote={scenePowerNote}
                        dcSignals={sceneDcSignals}
                        acSignals={sceneAcSignals}
                        metrics={sceneMetrics}
                        canvasAction={
                          liteDevicePowerCommand ? (
                            <CompactDeviceSetpointControl
                              inputValue={deviceSetpointInput}
                              lastSetpointDisplay={liteDevicePowerCommand.last_set_display}
                              lastSetpointAt={liteDevicePowerCommand.last_set_at}
                              actionBusy={deviceSetpointActionBusy}
                              actionError={deviceSetpointActionError}
                              actionMessage={deviceSetpointActionMessage}
                              onInputChange={(value) => {
                                setDeviceSetpointInput(value);
                                setDeviceSetpointActionError(null);
                                setDeviceSetpointActionMessage(null);
                              }}
                              onApply={() => void handleApplyDeviceSetpoint()}
                            />
                          ) : null
                        }
                        headerAction={
                          <div className="lite-detail-actions">
                            <button
                              className="secondary-button inverter-scene-focus-button"
                              type="button"
                              onClick={() => setSelectedDeviceId(null)}
                            >
                              Torna all'impianto
                            </button>
                            <button
                              className="secondary-button inverter-scene-focus-button"
                              type="button"
                              onClick={() => setDashboardMode("pro")}
                            >
                              Apri in Pro
                            </button>
                          </div>
                        }
                      />
                    </section>

                    <section className="group-board group-board--compact">
                      {activeGroups.slice(0, 4).map((group) => (
                        <DataGroupCard key={group.title} group={group} />
                      ))}
                    </section>
                  </>
                ) : (
                  <>
                  <section className={`stage-panel lite-hero-panel lite-hero-panel--${liteHeroMessage.tone}`}>
                    <div className="lite-hero-panel__copy">
                      <p className="panel-kicker">Dashboard Lite</p>
                      <h2>{liteHeroMessage.title}</h2>
                      <p className="lite-hero-panel__note">{liteHeroMessage.note}</p>
                    </div>
                    <PlantPowerControlCard
                      label="Stato impianto"
                      loading={loading}
                      value={summary ? formatCompactPowerKw(summary.total_power_kw) : "--"}
                      caption={
                        summary
                          ? `${summary.online_devices}/${summary.total_devices} inverter online`
                          : "Nessun dispositivo disponibile"
                      }
                      inputValue={fleetSetpointInput}
                      actionBusy={fleetSetpointActionBusy}
                      actionError={fleetSetpointActionError}
                      onInputChange={(value) => {
                        setFleetSetpointInput(value);
                        setFleetSetpointInputDirty(true);
                        setFleetSetpointActionError(null);
                      }}
                      onApply={() => void handleApplyFleetSetpoint()}
                      onClear={() => void handleClearFleetSetpoint()}
                    />
                  </section>

                  <section className="stage-panel stage-panel--history">
                    <div className="stage-header">
                      <div>
                        <p className="panel-kicker">Andamento impianto</p>
                        <h2>Produzione attiva nel tempo</h2>
                      </div>
                      <div className="stage-header-actions">
                        <span className="stage-meta">
                          Trend semplificato della potenza totale prodotta
                        </span>
                      </div>
                    </div>
                    <PowerHistoryChart
                      labels={powerHistory?.labels ?? []}
                      series={liteFleetChartSeries}
                      loading={loading}
                      errorMessage={powerHistoryError}
                      emptyTitle="Storico impianto non ancora disponibile"
                      emptyMessage="La dashboard lite mostrerà il trend non appena il backend avrà campioni reali di potenza."
                      height={250}
                      rangePreset={powerHistoryRange.presetId}
                      rangeStart={powerHistoryRange.startIso}
                      rangeEnd={powerHistoryRange.endIso}
                      rangeIsLive={powerHistoryRange.isLive}
                      rangeMode={powerHistoryRange.mode}
                      onRangePresetChange={handlePowerHistoryRangePresetChange}
                      onRangeShift={handlePowerHistoryRangeShift}
                      onRangeJumpToLive={handlePowerHistoryJumpToLive}
                      onRangeCustomApply={handlePowerHistoryCustomRangeApply}
                    />
                  </section>

                  <section className="stage-panel">
                    <div className="stage-header">
                      <div>
                        <p className="panel-kicker">Inverter</p>
                        <h2>Dispositivi in evidenza</h2>
                      </div>
                      <div className="stage-header-actions">
                        <span className="stage-meta">
                          L'alberatura completa resta sempre disponibile a sinistra
                        </span>
                      </div>
                    </div>
                    {liteDevices.length > 0 ? (
                      <div className="lite-device-grid">
                        {liteDevices.slice(0, 6).map((device) => (
                          <LiteDeviceCard
                            key={device.device_id}
                            device={device}
                            currentPower={devicePowerMap[device.device_id]}
                            onOpenPro={() => {
                              setDashboardMode("pro");
                              setSelectedDeviceId(device.device_id);
                              setMobileStageTab("live");
                            }}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="detail-empty">
                        Nessun inverter configurato. Usa la vista Pro per aggiungere dispositivi e
                        completare il commissioning.
                      </div>
                    )}
                  </section>
                  </>
                )
              ) : !selectedDevice ? (
                <>
                  <section
                    className={`stage-panel lite-hero-panel lite-hero-panel--${liteHeroMessage.tone} mobile-stage-panel mobile-stage-panel--live ${
                      !isMobileLayout || activeMobileStageTab === "live"
                        ? "mobile-stage-panel--active"
                        : ""
                    }`}
                  >
                    <div className="lite-hero-panel__copy">
                      <p className="panel-kicker">Dashboard Pro</p>
                      <h2>{liteHeroMessage.title}</h2>
                      <p className="lite-hero-panel__note">{liteHeroMessage.note}</p>
                    </div>
                    <PlantPowerControlCard
                      label="Stato impianto"
                      loading={loading}
                      value={summary ? formatCompactPowerKw(summary.total_power_kw) : "--"}
                      caption={
                        summary
                          ? `${summary.online_devices}/${summary.total_devices} inverter online`
                          : "Nessun dispositivo disponibile"
                      }
                      inputValue={fleetSetpointInput}
                      actionBusy={fleetSetpointActionBusy}
                      actionError={fleetSetpointActionError}
                      onInputChange={(value) => {
                        setFleetSetpointInput(value);
                        setFleetSetpointInputDirty(true);
                        setFleetSetpointActionError(null);
                      }}
                      onApply={() => void handleApplyFleetSetpoint()}
                      onClear={() => void handleClearFleetSetpoint()}
                    />
                  </section>
                  <section
                    className={`stage-panel mobile-stage-panel mobile-stage-panel--history ${
                      !isMobileLayout || activeMobileStageTab === "history"
                        ? "mobile-stage-panel--active"
                        : ""
                    }`}
                  >
                    <div className="stage-header">
                      <div>
                        <p className="panel-kicker">Panoramica impianto</p>
                        <h2>Potenza attiva di impianto</h2>
                      </div>
                      <div className="stage-header-actions">
                        <span className="stage-meta">
                          Storico aggregato e andamento reale della resa complessiva
                        </span>
                        <button
                          className="secondary-button"
                          type="button"
                          onClick={() => setIsAdvancedFleetHistoryOpen(true)}
                        >
                          Storico avanzato
                        </button>
                      </div>
                    </div>
                    <PowerHistoryChart
                      labels={powerHistory?.labels ?? []}
                      series={fleetChartSeries}
                      loading={loading}
                      errorMessage={powerHistoryError}
                      emptyTitle="Storico reale di impianto non ancora disponibile"
                      emptyMessage="I KPI live di impianto sono gia disponibili, ma il backend non ha ancora restituito campioni storici reali di potenza per questa vista."
                      height={250}
                      rangePreset={powerHistoryRange.presetId}
                      rangeStart={powerHistoryRange.startIso}
                      rangeEnd={powerHistoryRange.endIso}
                      rangeIsLive={powerHistoryRange.isLive}
                      rangeMode={powerHistoryRange.mode}
                      onRangePresetChange={handlePowerHistoryRangePresetChange}
                      onRangeShift={handlePowerHistoryRangeShift}
                      onRangeJumpToLive={handlePowerHistoryJumpToLive}
                      onRangeCustomApply={handlePowerHistoryCustomRangeApply}
                    />
                  </section>
                  <section
                    className={`group-board group-board--compact mobile-stage-panel mobile-stage-panel--live ${
                      !isMobileLayout || activeMobileStageTab === "live"
                        ? "mobile-stage-panel--active"
                        : ""
                    }`}
                  >
                    {activeGroups.slice(0, 4).map((group) => (
                      <DataGroupCard key={group.title} group={group} />
                    ))}
                  </section>
                </>
              ) : (
                <>
                  <section
                    className={`stage-panel stage-panel--scene mobile-stage-panel mobile-stage-panel--live ${
                      !isMobileLayout || activeMobileStageTab === "live"
                        ? "mobile-stage-panel--active"
                        : ""
                    }`}
                  >
                    <InverterFlowScene
                      eyebrow="Vista inverter"
                      title={sceneTitle}
                      caption={sceneCaption}
                      status={sceneStatus}
                      statusLabel={translateStatusLabel(sceneStatus)}
                      powerLabel="Potenza dispositivo"
                      powerValue={scenePowerValue}
                      powerNote={scenePowerNote}
                      dcSignals={sceneDcSignals}
                      acSignals={sceneAcSignals}
                      metrics={sceneMetrics}
                      headerAction={
                        <button
                          className="secondary-button inverter-scene-focus-button"
                          type="button"
                          onClick={() => setIsFocusPanelOpen(true)}
                        >
                          Apri focus tecnico
                        </button>
                      }
                    />
                  </section>
                  <section
                    className={`group-board group-board--compact mobile-stage-panel mobile-stage-panel--live ${
                      !isMobileLayout || activeMobileStageTab === "live"
                        ? "mobile-stage-panel--active"
                        : ""
                    }`}
                  >
                    {activeGroups.slice(0, 4).map((group) => (
                      <DataGroupCard key={group.title} group={group} />
                    ))}
                  </section>
                  <DeviceDetailPanel
                    deviceId={selectedDevice.device_id}
                    onClose={() => setSelectedDeviceId(null)}
                    layout="inline"
                    viewMode={
                      isMobileLayout
                        ? activeMobileStageTab === "history"
                          ? "history"
                          : activeMobileStageTab === "commands"
                            ? "commands"
                            : "live"
                        : "all"
                    }
                  />
                </>
              )}
            </main>

          </div>
        </div>
      </div>

      <AppFooter
        health={systemHealth}
        currentTime={footerTime}
        onOpenHealth={() => setIsSystemHealthOpen(true)}
      />

      {isCompactSidebarLayout ? (
        <div
          className={`fleet-drawer-backdrop ${
            isFleetDrawerOpen ? "fleet-drawer-backdrop--open" : ""
          }`}
          role="presentation"
          onClick={() => setIsFleetDrawerOpen(false)}
        >
          <aside
            className="fleet-drawer-panel"
            aria-label="Parco inverter"
            onClick={(event) => event.stopPropagation()}
          >
            {isOperatorMode ? (
              operatorSidebarContent
            ) : (
              <FleetSidebarContent
                summary={summary}
                loading={loading}
                error={error}
                availability={availability}
                devices={devices}
                selectedDeviceId={selectedDeviceId}
                devicePowerMap={devicePowerMap}
                deviceOverviewMap={deviceOverviewMap}
                onAddDevice={() => {
                  setIsFleetDrawerOpen(false);
                  openManualAddDevice();
                }}
                onOpenDiscovery={() => {
                  setIsFleetDrawerOpen(false);
                  openDiscoveryModal();
                }}
                onSelectFleet={() => {
                  setSelectedDeviceId(null);
                  setIsFleetDrawerOpen(false);
                  setMobileStageTab("live");
                }}
                onSelectDevice={(deviceId) => {
                  setSelectedDeviceId(deviceId);
                  setIsFleetDrawerOpen(false);
                  setMobileStageTab("live");
                }}
                onOpenSettings={(deviceId) => {
                  setSettingsDeviceId(deviceId);
                  setIsFleetDrawerOpen(false);
                }}
                discoveryActive={discoveryActive}
                discoveryResultCount={discoveryResultCount}
                viewMode={dashboardMode}
                onClose={() => setIsFleetDrawerOpen(false)}
              />
            )}
          </aside>
        </div>
      ) : null}

      {isFocusPanelOpen && dashboardMode === "pro" ? (
        <div
          className="focus-drawer-backdrop"
          role="presentation"
          onClick={() => setIsFocusPanelOpen(false)}
        >
          <aside
            className="focus-drawer-panel"
            aria-label={selectedDevice ? "Focus tecnico dispositivo" : "Focus operativo impianto"}
            onClick={(event) => event.stopPropagation()}
          >
            <FocusPanelContent
              selectedDevice={selectedDevice}
              railSummaryItems={railSummaryItems}
              liveFocusItems={liveFocusItems}
              onClose={() => setIsFocusPanelOpen(false)}
            />
          </aside>
        </div>
      ) : null}

      {isSystemHealthOpen ? (
        <SystemHealthDrawer
          health={systemHealth}
          loading={loading && systemHealth === null}
          error={systemHealthError}
          onClose={() => setIsSystemHealthOpen(false)}
        />
      ) : null}

      <OperatorComSettingsDrawer
        open={isOperatorComSettingsOpen}
        fleetControl={fleetControl}
        focusSection={operatorComSettingsFocus}
        onClose={() => setIsOperatorComSettingsOpen(false)}
        onRefreshSerialPorts={() => {
          void loadSerialPortOptions();
        }}
      >
        {operatorComSettingsFocus === "slave" ? (
          <OperatorComSettingsSection
            eyebrow="Slave CCI"
            title="Slave Modbus TCP"
            note="Gestisci host, porta e unità del nostro slave dedicato al CCI, con stato runtime e comandi rapidi."
            icon={<SlaveBridgeIcon />}
            active
          >
            <OperatorModbusSlaveSettingsCard
              fleetControl={fleetControl}
              draft={slaveSettingsDraft}
              busy={slaveSettingsBusy}
              dirty={slaveSettingsDirty}
              error={slaveSettingsError}
              message={slaveSettingsMessage}
              onChange={handleSlaveSettingsDraftChange}
              onApply={() => void handleApplySlaveSettings()}
              onReset={resetSlaveSettingsDraft}
            />
          </OperatorComSettingsSection>
        ) : (
          <OperatorComSettingsSection
            eyebrow="Bridge seriale"
            title="HSM verso inverter"
            note="Configura il passaggio del traffico HSM sulla COM inverter gestita dall'app, con contatori e diagnostica separati."
            icon={<HsmBridgeIcon />}
            tone="accent"
            active
          >
            <OperatorHsmBridgeRuntimeGrid fleetControl={fleetControl} />
            <OperatorHsmBridgeSettingsCard
              fleetControl={fleetControl}
              draft={hsmBridgeSettingsDraft}
              serialPorts={serialPorts}
              busy={hsmBridgeSettingsBusy}
              dirty={hsmBridgeSettingsDirty}
              error={hsmBridgeSettingsError}
              message={hsmBridgeSettingsMessage}
              onChange={handleHsmBridgeSettingsDraftChange}
              onApply={() => void handleApplyHsmBridgeSettings()}
              onReset={resetHsmBridgeSettingsDraft}
            />
          </OperatorComSettingsSection>
        )}
      </OperatorComSettingsDrawer>

      <DrawerErrorBoundary
        onClose={() => setIsSystemSettingsOpen(false)}
        resetKey={isSystemSettingsOpen ? "open" : "closed"}
        title="LAN Settings"
      >
        <SystemSettingsDrawer
          open={isSystemSettingsOpen}
          onClose={() => setIsSystemSettingsOpen(false)}
          onPendingChange={handleNetworkPendingChange}
        />
      </DrawerErrorBoundary>

      <AdvancedHistoryDrawer
        open={isAdvancedFleetHistoryOpen}
        scope="fleet"
        onClose={() => setIsAdvancedFleetHistoryOpen(false)}
      />

      <OperatorProvisioningDrawer
        open={isOperatorProvisioningOpen}
        existingDevices={devices}
        cancelRequestToken={operatorProvisioningCancelRequestToken}
        onClose={() => setIsOperatorProvisioningOpen(false)}
        onBusyChange={setOperatorProvisioningBusy}
        onProgressChange={setOperatorProvisioningProgress}
        onScanBusyChange={setOperatorScanBusy}
        onScanResultCountChange={setDiscoveryResultCount}
        onCreated={async (createdDevices) => {
          if (createdDevices.length > 0) {
            setFirstConnectWatch({
              startedAt: Date.now(),
              targets: createdDevices.map((device) => ({
                deviceId: device.device_id,
                name: device.name,
              })),
            });
          }
          await loadDashboardData();
        }}
      />

      <DeviceDiscoveryModal
        open={isDiscoveryOpen}
        onClose={() => setIsDiscoveryOpen(false)}
        existingDevices={devices}
        onBrowsingStateChange={setIsDiscoveryRunning}
        onResultCountChange={setDiscoveryResultCount}
        onSelectResult={handleDiscoverySelection}
      />

      {isAddDeviceOpen ? (
        <AddDeviceModal
          onClose={closeAddDevice}
          onCreated={loadDashboardData}
          prefill={addDevicePrefill}
        />
      ) : null}

      <AppActionDialog
        open={deleteDialog !== null}
        title={deleteDialogTitle}
        message={deleteDialogMessage}
        tone="warning"
        confirmLabel={deleteDialogConfirmLabel}
        onConfirm={handleDeleteDialogConfirm}
        onClose={handleDeleteDialogClose}
        cancelLabel="Annulla"
        busy={deleteDialogBusy}
        confirmVariant={bulkDeleteDialog?.stage === "initial" ? "accent" : "danger"}
      />

      <AppActionDialog
        open={noticeDialog !== null}
        title={noticeDialog?.title ?? ""}
        message={noticeDialog?.message ?? ""}
        tone={noticeDialog?.tone ?? "info"}
        confirmLabel={noticeDialog?.confirmLabel ?? "OK"}
        onConfirm={() => setNoticeDialog(null)}
        onClose={() => setNoticeDialog(null)}
      />

      {settingsDevice ? (
        <DeviceConnectionDrawer
          device={settingsDevice}
          onClose={() => setSettingsDeviceId(null)}
          onDeleted={async (deviceId) => {
            setSelectedDeviceId((current) => (current === deviceId ? null : current));
            setSettingsDeviceId(null);
            setDevices((current) => current.filter((device) => device.device_id !== deviceId));
            setDevicePowerMap((current) => {
              const next = { ...current };
              delete next[deviceId];
              return next;
            });
            setDeviceOverviewMap((current) => {
              const next = { ...current };
              delete next[deviceId];
              return next;
            });
            await loadDashboardData(false);
          }}
          onUpdated={async () => {
            await loadDashboardData(false);
          }}
        />
      ) : null}
      </div>
    </>
  );
}
