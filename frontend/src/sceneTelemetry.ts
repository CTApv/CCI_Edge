import type { DeviceOverview, DeviceOverviewTelemetryPoint } from "./api";
import { buildOrderedTelemetrySections } from "./telemetryPresentation";

type TelemetrySignalDefinition = {
  label: string;
  keys: string[];
  terms: string[];
  sectionTerms: string[];
  units: string[];
  excludeTerms?: string[];
};

export type TelemetrySignal = {
  label: string;
  value: string;
  estimated?: boolean;
  estimateNote?: string;
};

type TelemetrySignalSelection = TelemetrySignal & {
  point?: DeviceOverviewTelemetryPoint;
  numericValue?: number;
  normalizedUnit?: string;
};

const estimatedPowerFormatter = new Intl.NumberFormat("it-IT", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 3,
});

const dashboardSignalFormatter = new Intl.NumberFormat("it-IT", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 3,
});

function normalizeSearchValue(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function normalizeUnit(value: string): string {
  return normalizeSearchValue(value).replace(/\s+/g, "");
}

function formatTelemetryPointValue(point: DeviceOverviewTelemetryPoint): string {
  return point.unit ? `${point.display_value} ${point.unit}` : point.display_value;
}

function formatDashboardSignalValue(value: number, unit: string): string {
  const displayValue = dashboardSignalFormatter.format(value);
  return unit ? `${displayValue} ${unit}` : displayValue;
}

function toNumericValue(value: DeviceOverviewTelemetryPoint["value"]): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function toPowerInKilowatts(selection: TelemetrySignalSelection | undefined): number | null {
  if (!selection || selection.numericValue === undefined) {
    return null;
  }

  switch (selection.normalizedUnit) {
    case "kw":
      return selection.numericValue;
    case "w":
      return selection.numericValue / 1_000;
    case "mw":
      return selection.numericValue * 1_000;
    case "gw":
      return selection.numericValue * 1_000_000;
    default:
      return null;
  }
}

function toVoltageInVoltsFromSelection(
  selection: TelemetrySignalSelection | undefined,
): number | null {
  if (!selection || selection.numericValue === undefined) {
    return null;
  }

  switch (selection.normalizedUnit) {
    case "v":
      return selection.numericValue;
    case "kv":
      return selection.numericValue * 1_000;
    case "mv":
      return selection.numericValue / 1_000;
    default:
      return null;
  }
}

function toCurrentInAmperesFromSelection(
  selection: TelemetrySignalSelection | undefined,
): number | null {
  if (!selection || selection.numericValue === undefined) {
    return null;
  }

  switch (selection.normalizedUnit) {
    case "a":
      return selection.numericValue;
    case "ka":
      return selection.numericValue * 1_000;
    case "ma":
      return selection.numericValue / 1_000;
    default:
      return null;
  }
}

function estimateDcPowerSignal(
  voltageSignal: TelemetrySignalSelection | undefined,
  currentSignal: TelemetrySignalSelection | undefined,
): TelemetrySignal | null {
  if (!voltageSignal || !currentSignal) {
    return null;
  }

  const voltageV = toVoltageInVoltsFromSelection(voltageSignal);
  const currentA = toCurrentInAmperesFromSelection(currentSignal);

  if (voltageV === null || currentA === null) {
    return null;
  }

  const powerKw = (voltageV * currentA) / 1_000;

  if (!Number.isFinite(powerKw)) {
    return null;
  }

  return {
    label: "Potenza DC",
    value: `${estimatedPowerFormatter.format(powerKw)} kW`,
    estimated: true,
    estimateNote: "Valore stimato da tensione DC x corrente DC, non letto direttamente dall'inverter.",
  };
}

function normalizeLikelyRawPower(value: number, expectedPowerKw: number | null): number {
  if (expectedPowerKw === null || expectedPowerKw <= 0 || !Number.isFinite(expectedPowerKw)) {
    return value;
  }

  const candidates = [value, value / 10, value / 100, value / 1_000];
  const ranked = candidates
    .map((candidate) => ({
      value: candidate,
      score: Math.abs(Math.log(Math.max(Math.abs(candidate), 0.001) / expectedPowerKw)),
    }))
    .sort((left, right) => left.score - right.score);
  const best = ranked[0];
  const currentScore = Math.abs(Math.log(Math.max(Math.abs(value), 0.001) / expectedPowerKw));

  if (!best) {
    return value;
  }

  const originalIsClearlyHigh = Math.abs(value) > expectedPowerKw * 2.25;
  const candidateIsPlausible = Math.abs(best.value) >= expectedPowerKw * 0.25;
  const candidateImprovesEnough = best.score + 0.45 < currentScore;

  return originalIsClearlyHigh && candidateIsPlausible && candidateImprovesEnough
    ? best.value
    : value;
}

function normalizeLikelyRawVoltage(value: number, label: string): number {
  const absoluteValue = Math.abs(value);
  const scaledValue = value / 10;
  const scaledAbsoluteValue = Math.abs(scaledValue);

  if (label === "Tensione AC") {
    if (absoluteValue > 1_000 && absoluteValue <= 10_000 && scaledAbsoluteValue <= 1_000) {
      return scaledValue;
    }
    return value;
  }

  if (absoluteValue > 1_500 && absoluteValue <= 15_000 && scaledAbsoluteValue <= 1_500) {
    return scaledValue;
  }

  return value;
}

function normalizeLikelyRawFrequency(value: number): number {
  const absoluteValue = Math.abs(value);
  if (absoluteValue >= 4_000 && absoluteValue <= 7_000) {
    return value / 100;
  }
  if (absoluteValue >= 400 && absoluteValue <= 700) {
    return value / 10;
  }
  return value;
}

function scoreCurrentCandidate(
  candidate: number,
  expectedCurrentA: number | null,
): number {
  if (expectedCurrentA === null || expectedCurrentA <= 0 || !Number.isFinite(expectedCurrentA)) {
    return Number.POSITIVE_INFINITY;
  }

  const absoluteCandidate = Math.abs(candidate);
  if (absoluteCandidate <= 0) {
    return Number.POSITIVE_INFINITY;
  }

  return Math.abs(Math.log(absoluteCandidate / expectedCurrentA));
}

function buildSelectionFingerprint(selection: TelemetrySignalSelection | undefined): string {
  if (!selection?.point) {
    return "";
  }
  return normalizeSearchValue(
    `${selection.point.key} ${selection.point.label} ${selection.point.section}`,
  );
}

function isLikelySingleDcInputCurrent(selection: TelemetrySignalSelection | undefined): boolean {
  const fingerprint = buildSelectionFingerprint(selection);
  return (
    fingerprint.includes("pv1") ||
    fingerprint.includes("pv 1") ||
    fingerprint.includes("pv_1") ||
    fingerprint.includes("input1") ||
    fingerprint.includes("input 1") ||
    fingerprint.includes("input_1") ||
    fingerprint.includes("ingresso 1")
  );
}

function normalizeLikelyRawSingleInputCurrent(value: number, preferCentiampScale: boolean): number {
  const absoluteValue = Math.abs(value);

  if (preferCentiampScale && absoluteValue >= 100 && absoluteValue <= 10_000) {
    const scaledValue = value / 100;
    if (Math.abs(scaledValue) <= 80) {
      return scaledValue;
    }
  }

  if (absoluteValue >= 100 && absoluteValue <= 1_000) {
    const scaledValue = value / 10;
    if (Math.abs(scaledValue) <= 80) {
      return scaledValue;
    }
  }

  return value;
}

function normalizeLikelyRawCurrent(value: number, expectedCurrentA: number | null): number {
  if (expectedCurrentA === null || expectedCurrentA <= 0) {
    return value;
  }

  const candidates = [value, value / 10, value / 100, value / 1_000];
  const ranked = candidates
    .map((candidate) => ({
      value: candidate,
      score: scoreCurrentCandidate(candidate, expectedCurrentA),
    }))
    .sort((left, right) => left.score - right.score);

  const best = ranked[0];
  const currentScore = scoreCurrentCandidate(value, expectedCurrentA);

  if (!best || !Number.isFinite(best.score)) {
    return value;
  }

  const originalIsClearlyHigh = Math.abs(value) > expectedCurrentA * 2.25;
  const candidateIsPlausible = Math.abs(best.value) >= expectedCurrentA * 0.35;
  const candidateImprovesEnough = best.score + 0.45 < currentScore;

  return originalIsClearlyHigh && candidateIsPlausible && candidateImprovesEnough
    ? best.value
    : value;
}

function normalizeSelectedElectricalSignals(
  overview: DeviceOverview,
  selections: TelemetrySignalSelection[],
): TelemetrySignalSelection[] {
  const normalizedSelections = selections.map((selection) => ({ ...selection }));
  const overviewPowerKw =
    Number.isFinite(overview.metrics.power_kw) && overview.metrics.power_kw > 0
      ? overview.metrics.power_kw
      : null;

  for (const selection of normalizedSelections) {
    if (!selection.point || selection.numericValue === undefined) {
      continue;
    }

    if (selection.label.includes("Potenza") && selection.normalizedUnit === "kw") {
      const nextValue = normalizeLikelyRawPower(selection.numericValue, overviewPowerKw);
      if (nextValue !== selection.numericValue) {
        selection.numericValue = nextValue;
        selection.value = formatDashboardSignalValue(nextValue, selection.point.unit);
      }
    }

    if (selection.label.includes("Tensione")) {
      const nextValue = normalizeLikelyRawVoltage(selection.numericValue, selection.label);
      if (nextValue !== selection.numericValue) {
        selection.numericValue = nextValue;
        selection.value = formatDashboardSignalValue(nextValue, selection.point.unit);
      }
    }

    if (selection.label.includes("Frequenza")) {
      const nextValue = normalizeLikelyRawFrequency(selection.numericValue);
      if (nextValue !== selection.numericValue) {
        selection.numericValue = nextValue;
        selection.value = formatDashboardSignalValue(nextValue, selection.point.unit);
      }
    }
  }

  const dcPowerKw = toPowerInKilowatts(
    normalizedSelections.find((signal) => signal.label === "Potenza DC"),
  );
  const dcVoltageV = toVoltageInVoltsFromSelection(
    normalizedSelections.find((signal) => signal.label === "Tensione DC"),
  );
  const dcExpectedCurrentA =
    dcPowerKw !== null && dcVoltageV !== null && dcVoltageV > 0
      ? (dcPowerKw * 1_000) / dcVoltageV
      : null;

  const dcCurrentSignal = normalizedSelections.find((signal) => signal.label === "Corrente DC");
  if (dcCurrentSignal?.point && dcCurrentSignal.numericValue !== undefined) {
    const deviceFingerprint = normalizeSearchValue(
      `${overview.device.brand} ${overview.device.model}`,
    );
    const nextValue = isLikelySingleDcInputCurrent(dcCurrentSignal)
      ? normalizeLikelyRawSingleInputCurrent(
          dcCurrentSignal.numericValue,
          deviceFingerprint.includes("huawei"),
        )
      : normalizeLikelyRawCurrent(dcCurrentSignal.numericValue, dcExpectedCurrentA);
    if (nextValue !== dcCurrentSignal.numericValue) {
      dcCurrentSignal.numericValue = nextValue;
      dcCurrentSignal.value = formatDashboardSignalValue(nextValue, dcCurrentSignal.point.unit);
    }
  }

  const acVoltageV = toVoltageInVoltsFromSelection(
    normalizedSelections.find((signal) => signal.label === "Tensione AC"),
  );
  const acExpectedCurrentA =
    overviewPowerKw !== null && acVoltageV !== null && acVoltageV > 0
      ? (overviewPowerKw * 1_000) / (Math.sqrt(3) * acVoltageV)
      : null;
  const acCurrentSignal = normalizedSelections.find((signal) => signal.label === "Corrente AC");
  if (acCurrentSignal?.point && acCurrentSignal.numericValue !== undefined) {
    const nextValue = normalizeLikelyRawCurrent(acCurrentSignal.numericValue, acExpectedCurrentA);
    if (nextValue !== acCurrentSignal.numericValue) {
      acCurrentSignal.numericValue = nextValue;
      acCurrentSignal.value = formatDashboardSignalValue(nextValue, acCurrentSignal.point.unit);
    }
  }

  return normalizedSelections;
}

function countMatches(source: string, terms: string[]): number {
  return terms.reduce(
    (total, term) => (source.includes(normalizeSearchValue(term)) ? total + 1 : total),
    0,
  );
}

function hasExcludedTerm(source: string, excludeTerms: string[]): boolean {
  return excludeTerms.some((term) => source.includes(normalizeSearchValue(term)));
}

function scoreTelemetryPoint(
  point: DeviceOverviewTelemetryPoint,
  definition: TelemetrySignalDefinition,
): number {
  if (point.value === null) {
    return Number.NEGATIVE_INFINITY;
  }

  const fingerprint = normalizeSearchValue(`${point.section} ${point.label} ${point.key}`);
  const sectionFingerprint = normalizeSearchValue(point.section);
  const normalizedUnit = normalizeUnit(point.unit);

  if (hasExcludedTerm(fingerprint, definition.excludeTerms ?? [])) {
    return Number.NEGATIVE_INFINITY;
  }

  let score = 0;

  const exactKeyIndex = definition.keys.findIndex((candidateKey) => candidateKey === point.key);
  if (exactKeyIndex >= 0) {
    score += 1_000 - exactKeyIndex * 10;
  }

  const termHits = countMatches(fingerprint, definition.terms);
  const sectionHits = countMatches(sectionFingerprint, definition.sectionTerms);

  if (termHits > 0) {
    score += termHits * 70;
  }

  if (sectionHits > 0) {
    score += sectionHits * 45;
  }

  if (definition.units.length > 0) {
    if (point.unit) {
      if (!definition.units.includes(normalizedUnit)) {
        return Number.NEGATIVE_INFINITY;
      }

      score += 60;
    }
  }

  if (fingerprint.includes("phase a") || fingerprint.includes("fase a") || fingerprint.includes(" l1")) {
    score += 8;
  }
  if (fingerprint.includes("mean") || fingerprint.includes("total") || fingerprint.includes("totale")) {
    score += 6;
  }
  if (fingerprint.includes("meter")) {
    score += 4;
  }

  if (exactKeyIndex < 0 && termHits === 0 && sectionHits === 0) {
    return Number.NEGATIVE_INFINITY;
  }

  return score;
}

const COMMON_EXCLUDE_TERMS = [
  "fault",
  "guasto",
  "allarme",
  "alarm",
  "warning",
  "errore",
  "error",
];

export const DC_SIGNAL_DEFINITIONS: TelemetrySignalDefinition[] = [
  {
    label: "Potenza DC",
    keys: [
      "dc_power_kw",
      "dc_input_power_kw",
      "input_power_kw",
      "dc_input1_power_kw",
      "dc_input2_power_kw",
      "dc_input_1_power_kw",
      "dc_input_2_power_kw",
      "dc_power_total_kw",
      "dc1_power_kw",
      "dc2_power_kw",
      "dc3_power_kw",
      "pv1_power_kw",
      "pv2_power_kw",
      "pv_1_power_kw",
      "pv_2_power_kw",
      "pv_3_power_kw",
      "pv_power_kw",
      "pv_input_power_kw",
      "total_dc_power_w",
      "dc_link_power_kw",
      "storage_power_w",
      "esu1_power_w",
      "esu2_power_w",
    ],
    terms: [
      "potenza dc",
      "dc power",
      "input power",
      "potenza ingresso",
      "potenza fv",
      "dc input power",
      "dc-link power",
      "potenza accumulo",
      "charge/discharge power",
    ],
    sectionTerms: ["ingresso dc", "ingresso fv", "dc bus", "accumulo", "storage", "battery"],
    units: ["kw", "w", "mw", "gw"],
    excludeTerms: [...COMMON_EXCLUDE_TERMS, "reactive", "reattiva", "apparent", "apparente"],
  },
  {
    label: "Tensione DC",
    keys: [
      "dc_voltage_v",
      "dc_link_voltage_v",
      "pv1_voltage_v",
      "pv2_voltage_v",
      "pv3_voltage_v",
      "pv_1_voltage_v",
      "pv_2_voltage_v",
      "pv_3_voltage_v",
      "dc_input1_voltage_v",
      "dc_input2_voltage_v",
      "dc_input_1_voltage_v",
      "dc_input_2_voltage_v",
      "storage_bus_voltage_v",
      "esu1_bus_voltage_v",
      "esu2_bus_voltage_v",
      "average_dc_link_voltage_v",
      "voltage_on_dc_input_1_v",
    ],
    terms: [
      "tensione dc",
      "dc voltage",
      "dc-link voltage",
      "bus voltage",
      "tensione bus",
      "tensione fv",
      "voltage on dc input",
      "tensione celle",
    ],
    sectionTerms: ["ingresso dc", "ingresso fv", "dc bus", "accumulo", "storage", "battery"],
    units: ["v", "kv"],
    excludeTerms: [...COMMON_EXCLUDE_TERMS, "frequency", "frequenza", "current", "corrente"],
  },
  {
    label: "Corrente DC",
    keys: [
      "dc_current_a",
      "pv1_current_a",
      "pv2_current_a",
      "pv3_current_a",
      "pv_1_current_a",
      "pv_2_current_a",
      "pv_3_current_a",
      "dc_input1_current_a",
      "dc_input2_current_a",
      "dc_input_1_current_a",
      "dc_input_2_current_a",
      "storage_bus_current_a",
      "esu1_bus_current_a",
      "esu2_bus_current_a",
      "current_on_dc_input_1_a",
    ],
    terms: [
      "corrente dc",
      "dc current",
      "bus current",
      "corrente fv",
      "current on dc input",
      "corrente celle",
    ],
    sectionTerms: ["ingresso dc", "ingresso fv", "dc bus", "accumulo", "storage", "battery"],
    units: ["a"],
    excludeTerms: [...COMMON_EXCLUDE_TERMS, "frequency", "frequenza", "voltage", "tensione"],
  },
];

export const AC_SIGNAL_DEFINITIONS: TelemetrySignalDefinition[] = [
  {
    label: "Tensione AC",
    keys: [
      "ac_voltage_v",
      "grid_voltage_v",
      "mains_voltage_v",
      "mains_voltage_a_v",
      "ac_voltage_l2_v",
      "ac_voltage_l3_v",
      "grid_voltage_r_v",
      "grid_voltage_s_v",
      "grid_voltage_t_v",
      "grid_voltage_rn_v",
      "grid_voltage_sn_v",
      "grid_voltage_tn_v",
      "grid_voltage_l1n_v",
      "grid_voltage_l2n_v",
      "grid_voltage_l3n_v",
      "phase_a_voltage_v",
      "phase_b_voltage_v",
      "phase_c_voltage_v",
      "phase_l1n_voltage_v",
      "phase_l2n_voltage_v",
      "phase_l3n_voltage_v",
      "line_voltage_ab_v",
      "line_voltage_bc_v",
      "line_voltage_ca_v",
      "mean_grid_voltage_v",
      "meter_phase_a_voltage_v",
      "meter_grid_voltage_a_v",
      "voltage_ac_phase_1_v",
    ],
    terms: [
      "tensione rete",
      "grid voltage",
      "mains voltage",
      "ac voltage",
      "line voltage",
      "tensione ab",
      "tensione fase",
      "voltage ac",
    ],
    sectionTerms: ["rete ac", "mains", "grid", "ac", "contatore rete", "meter"],
    units: ["v", "kv"],
    excludeTerms: [...COMMON_EXCLUDE_TERMS, "frequency", "frequenza", "current", "corrente"],
  },
  {
    label: "Corrente AC",
    keys: [
      "ac_current_a",
      "grid_current_a",
      "power_supply_current_a",
      "current_a_a",
      "ac_current_l2_a",
      "ac_current_l3_a",
      "grid_current_r_a",
      "grid_current_s_a",
      "grid_current_t_a",
      "grid_current_l1_a",
      "grid_current_l2_a",
      "grid_current_l3_a",
      "phase_a_current_a",
      "phase_b_current_a",
      "phase_c_current_a",
      "phase_l1_current_a",
      "phase_l2_current_a",
      "phase_l3_current_a",
      "output_current_r_a",
      "meter_phase_a_current_a",
      "meter_grid_current_a_a",
      "current_ac_phase_1_a",
      "rms_current_a",
      "mean_output_current_a",
    ],
    terms: [
      "corrente rete",
      "grid current",
      "mains current",
      "ac current",
      "phase current",
      "corrente uscita",
      "output current",
      "power supply current",
    ],
    sectionTerms: ["rete ac", "mains", "grid", "ac", "contatore rete", "meter", "phase currents"],
    units: ["a"],
    excludeTerms: [...COMMON_EXCLUDE_TERMS, "frequency", "frequenza", "voltage", "tensione"],
  },
  {
    label: "Frequenza rete",
    keys: [
      "grid_frequency_hz",
      "mains_frequency_hz",
      "ac_frequency_hz",
      "phase_a_frequency_hz",
      "grid_frequency_r_hz",
      "grid_frequency_s_hz",
      "grid_frequency_t_hz",
      "mean_grid_frequency_hz",
      "meter_frequency_hz",
      "meter_grid_frequency_hz",
    ],
    terms: ["frequenza rete", "grid frequency", "mains frequency", "ac frequency", "frequenza ac"],
    sectionTerms: ["rete ac", "mains", "grid", "ac", "contatore rete", "meter"],
    units: ["hz"],
    excludeTerms: [...COMMON_EXCLUDE_TERMS, "voltage", "tensione", "current", "corrente"],
  },
];

export function pickTelemetrySignals(
  overview: DeviceOverview | null,
  definitions: TelemetrySignalDefinition[],
): TelemetrySignal[] {
  if (overview === null) {
    return definitions.map((definition) => ({ label: definition.label, value: "n.d." }));
  }

  const visiblePoints = buildOrderedTelemetrySections(overview.telemetry).flatMap(
    (section) => section.points,
  );
  const takenKeys = new Set<string>();

  const selections: TelemetrySignalSelection[] = definitions.map((definition) => {
    const bestMatch = visiblePoints
      .filter((point) => !takenKeys.has(point.key))
      .map((point) => ({
        point,
        score: scoreTelemetryPoint(point, definition),
      }))
      .filter((candidate) => Number.isFinite(candidate.score) && candidate.score > 0)
      .sort((left, right) => right.score - left.score)[0];

    if (!bestMatch) {
      return { label: definition.label, value: "n.d." };
    }

    takenKeys.add(bestMatch.point.key);
    return {
      label: definition.label,
      value: formatTelemetryPointValue(bestMatch.point),
      point: bestMatch.point,
      numericValue: toNumericValue(bestMatch.point.value) ?? undefined,
      normalizedUnit: normalizeUnit(bestMatch.point.unit),
    };
  });

  const normalizedSelections = normalizeSelectedElectricalSignals(overview, selections);

  const dcPowerIndex = normalizedSelections.findIndex((signal) => signal.label === "Potenza DC");
  const dcVoltageSignal = normalizedSelections.find((signal) => signal.label === "Tensione DC");
  const dcCurrentSignal = normalizedSelections.find((signal) => signal.label === "Corrente DC");

  if (dcPowerIndex >= 0 && normalizedSelections[dcPowerIndex]?.value === "n.d.") {
    const estimatedPowerSignal = estimateDcPowerSignal(dcVoltageSignal, dcCurrentSignal);
    if (estimatedPowerSignal) {
      normalizedSelections[dcPowerIndex] = estimatedPowerSignal;
    }
  }

  return normalizedSelections.map(
    ({ point: _point, numericValue: _numericValue, normalizedUnit: _normalizedUnit, ...signal }) =>
      signal,
  );
}
