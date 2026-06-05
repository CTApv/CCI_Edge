import type { DeviceOverviewTelemetryPoint } from "./api";

export type TelemetrySection = {
  section: string;
  points: DeviceOverviewTelemetryPoint[];
};

export type TelemetryMacroGroup = {
  key: string;
  title: string;
  note: string;
  sections: TelemetrySection[];
  pointCount: number;
};

const sectionTranslations: Record<string, string> = {
  general: "Generale",
  control: "Controllo",
  "thermal and overload": "Termico e sovraccarico",
  "digital i/o": "Ingressi e uscite digitali",
  counters: "Contatori",
  energy: "Energia",
  device: "Dispositivo",
  thermal: "Termico",
  "status and alarms": "Stato e allarmi",
  "power and current": "Potenza e correnti",
  "error environment": "Ambiente di errore",
  mains: "Rete AC",
  "phase currents": "Correnti di fase",
  identification: "Identificazione",
  stato: "Stato",
  allarmi: "Allarmi",
  "rete ac": "Rete AC",
  potenza: "Potenza",
  termico: "Termico",
  "ingresso fv": "Ingresso FV",
  targa: "Targa",
  "contatore rete": "Contatore rete",
  "schedulazione rete": "Schedulazione rete",
  "accumulo aggregato": "Accumulo aggregato",
  "accumulo unita 1": "Accumulo unita 1",
  "accumulo unita 2": "Accumulo unita 2",
  "accumulo pack esu 1": "Pack accumulo ESU 1",
  "accumulo pack esu 2": "Pack accumulo ESU 2",
  configurazione: "Configurazione",
  "protezioni rete": "Protezioni rete",
  "controllo reattivo": "Controllo reattivo",
  "controllo potenza": "Controllo potenza",
  "controllo impianto": "Controllo impianto",
  "controllo sistema": "Controllo sistema",
  sunspec: "SunSpec",
  "relay multifunzione": "Relay multifunzione",
};

const exactLabelTranslations: Record<string, string> = {
  "Reference percentage": "Percentuale di riferimento",
  "Digital inputs (hardware)": "Ingressi digitali hardware",
  "Digital inputs": "Ingressi digitali",
  "Digital outputs": "Uscite digitali",
  "Current error": "Errore corrente",
  Warnings: "Avvisi",
  "Controller status": "Stato controllore",
  "Energy counter 1": "Contatore energia 1",
  "Energy counter 2": "Contatore energia 2",
  "Error env. DC-link voltage": "Errore ambiente tensione DC-link",
  "Error env. output voltage": "Errore ambiente tensione uscita",
  Frequency: "Frequenza",
  "Power supply current": "Corrente alimentazione",
  "Mains voltage": "Tensione rete",
  "Current a": "Corrente fase A",
  "Current b": "Corrente fase B",
  "Current c": "Corrente fase C",
  "Current active power": "Potenza attiva istantanea",
  "Mains voltage a": "Tensione rete fase A",
  "Mains voltage b": "Tensione rete fase B",
  "Mains voltage c": "Tensione rete fase C",
  "Active power a": "Potenza attiva fase A",
  "Active power b": "Potenza attiva fase B",
  "Active power c": "Potenza attiva fase C",
  "Reactive power a": "Potenza reattiva fase A",
  "Reactive power b": "Potenza reattiva fase B",
  "Reactive power c": "Potenza reattiva fase C",
  "Mains reactive power": "Potenza reattiva rete",
  "DC power": "Potenza DC",
  "DC current": "Corrente DC",
  "Active energy": "Energia attiva",
  "Apparent power": "Potenza apparente",
  "Apparent power a": "Potenza apparente fase A",
  "Apparent power b": "Potenza apparente fase B",
  "Apparent power c": "Potenza apparente fase C",
  "Reactive power": "Potenza reattiva",
  "Solar status": "Stato solare",
  "Reference value reactive power": "Riferimento potenza reattiva",
  "Reference DC-link voltage": "Riferimento tensione DC-link",
  "Active power limit": "Limite potenza attiva",
  "Active power": "Potenza attiva",
  "Daily energy": "Energia giornaliera",
  "Total energy": "Energia totale",
  Temperature: "Temperatura",
  Status: "Stato",
  Voltage: "Tensione",
  Current: "Corrente",
  "Bus voltage": "Tensione bus",
  "Bus current": "Corrente bus",
  "Working mode": "Modalita operativa",
  "Fault ID": "ID guasto",
  "Part number": "Codice parte",
  "Model ID": "ID modello",
  "Startup time": "Ora avvio",
  "Shutdown time": "Ora arresto",
};

const labelReplacements: Array<[string, string]> = [
  ["DC-link", "DC-link"],
  ["DC link", "DC-link"],
  ["Active power", "Potenza attiva"],
  ["Output power", "Potenza uscita"],
  ["Power supply", "Alimentazione"],
  ["Power factor", "Fattore di potenza"],
  ["Daily energy", "Energia giornaliera"],
  ["Total energy", "Energia totale"],
  ["Energy counter", "Contatore energia"],
  ["Digital inputs", "Ingressi digitali"],
  ["Digital outputs", "Uscite digitali"],
  ["Mains voltage", "Tensione rete"],
  ["Phase currents", "Correnti di fase"],
  ["Controller status", "Stato controllore"],
  ["Reference", "Riferimento"],
  ["Percentage", "percentuale"],
  ["Voltage", "Tensione"],
  ["Current", "Corrente"],
  ["Temperature", "Temperatura"],
  ["Frequency", "Frequenza"],
  ["Status", "Stato"],
  ["Warnings", "Avvisi"],
  ["Warning", "Avviso"],
  ["Fault", "Guasto"],
  ["Alarm", "Allarme"],
  ["Error", "Errore"],
  ["Device", "Dispositivo"],
  ["Control", "Controllo"],
  ["Output", "Uscita"],
  ["Input", "Ingresso"],
  ["Working mode", "Modalita operativa"],
  ["Bus voltage", "Tensione bus"],
  ["Bus current", "Corrente bus"],
  ["Fault ID", "ID guasto"],
  ["Part number", "Codice parte"],
  ["Enable", "Abilitazione"],
  ["Limit", "Limite"],
  ["Counter", "Contatore"],
  ["Power", "Potenza"],
];

type PriorityRule = {
  priority: number;
  terms: string[];
};

const sectionPriorityRules: PriorityRule[] = [
  { priority: 0, terms: ["produzione", "production", "power and current", "potenza e corrente"] },
  { priority: 0, terms: ["misure inverter"] },
  { priority: 0, terms: ["misure der ac"] },
  { priority: 1, terms: ["mains", "ac", "grid", "rete", "phase currents", "correnti di fase"] },
  { priority: 2, terms: ["dc bus", "dc-link", "dc link", "dc", "input"] },
  { priority: 2, terms: ["misure der dc", "porte dc"] },
  { priority: 3, terms: ["thermal", "temperature", "termic", "overload"] },
  { priority: 4, terms: ["status and alarms", "status", "alarm", "fault", "warning", "stato"] },
  { priority: 4, terms: ["stati inverter", "heartbeat e diagnostica"] },
  { priority: 5, terms: ["control", "reference", "setpoint", "command", "comando"] },
  { priority: 5, terms: ["controllo potenza", "controllo impianto", "controllo der", "controllo sistema"] },
  { priority: 5, terms: ["controllo reattivo", "protezioni rete"] },
  { priority: 6, terms: ["counters", "energy", "meter", "counter", "contatori"] },
  { priority: 6, terms: ["energia inverter"] },
  { priority: 6, terms: ["contatore rete", "accumulo aggregato", "accumulo unita"] },
  { priority: 7, terms: ["device", "identification", "firmware", "version"] },
  { priority: 7, terms: ["dettagli inverter", "versione mappa modbus", "identificazione", "targa"] },
  { priority: 7, terms: ["capacita der"] },
  { priority: 7, terms: ["accumulo pack"] },
  { priority: 7, terms: ["configurazione"] },
  { priority: 7, terms: ["sunspec"] },
  { priority: 8, terms: ["digital i/o", "digital io", "digital", "i/o"] },
  { priority: 8, terms: ["relay multifunzione"] },
  { priority: 9, terms: ["error environment", "errors", "diagnostic", "diagnostica", "comunicazione"] },
];

const pointPriorityRules: PriorityRule[] = [
  { priority: 0, terms: ["active power", "power_kw", "power", "potenza attiva", "output power"] },
  { priority: 1, terms: ["daily energy", "today energy", "energia giornaliera"] },
  { priority: 2, terms: ["total energy", "lifetime energy", "energia totale", "energy"] },
  { priority: 3, terms: ["dc link voltage", "dc bus voltage", "voltage", "tensione"] },
  { priority: 4, terms: ["current", "corrente"] },
  { priority: 5, terms: ["frequency", "frequenza"] },
  { priority: 6, terms: ["temperature", "temperatura", "thermal"] },
  { priority: 7, terms: ["power factor", "cosphi", "cos phi"] },
  { priority: 8, terms: ["status", "mode", "state", "stato"] },
  { priority: 8, terms: ["soc", "batteria", "battery", "accumulo"] },
  { priority: 9, terms: ["alarm", "fault", "warning", "error", "allarme"] },
  { priority: 10, terms: ["enable", "reference", "limit", "command", "comando"] },
];

const telemetryMacroGroupDefinitions: Array<{
  key: string;
  title: string;
  note: string;
}> = [
  {
    key: "performance",
    title: "Produzione e resa",
    note: "Valori di potenza, energia e bilancio utili a capire subito quanto sta producendo il dispositivo.",
  },
  {
    key: "ac_grid",
    title: "Rete e uscita AC",
    note: "Misure lato rete, tensioni, correnti e grandezze di uscita collegate allo scambio con l'impianto.",
  },
  {
    key: "dc_storage",
    title: "Lato DC e accumulo",
    note: "Ingresso fotovoltaico, bus DC, batterie e dati di accumulo collegati al convertitore.",
  },
  {
    key: "status_control",
    title: "Stato, allarmi e controllo",
    note: "Stati macchina, allarmi, protezioni e parametri di controllo esposti dal modello.",
  },
  {
    key: "identity_service",
    title: "Identificazione e servizio",
    note: "Versioni, informazioni di targa, configurazione, dettagli di servizio e metadati tecnici.",
  },
  {
    key: "other",
    title: "Altri dati",
    note: "Valori aggiuntivi non classificati nelle categorie principali.",
  },
];

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

function replaceInsensitive(source: string, search: string, replacement: string): string {
  const escaped = search.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return source.replace(new RegExp(escaped, "gi"), replacement);
}

function resolvePriority(normalizedValue: string, rules: PriorityRule[], fallback: number): number {
  for (const rule of rules) {
    if (rule.terms.some((term) => normalizedValue.includes(term))) {
      return rule.priority;
    }
  }

  return fallback;
}

function sectionPriority(section: string): number {
  return resolvePriority(normalize(section), sectionPriorityRules, 20);
}

function pointPriority(point: DeviceOverviewTelemetryPoint): number {
  const fingerprint = normalize(`${point.section} ${point.label} ${point.key}`);
  return resolvePriority(fingerprint, pointPriorityRules, 20);
}

function resolveTelemetryMacroGroupKey(section: string): string {
  const normalizedSection = normalize(section);

  if (
    normalizedSection.includes("power") ||
    normalizedSection.includes("produzione") ||
    normalizedSection.includes("energy") ||
    normalizedSection.includes("counter") ||
    normalizedSection.includes("contatore") ||
    normalizedSection.includes("yield")
  ) {
    return "performance";
  }

  if (
    normalizedSection.includes("mains") ||
    normalizedSection.includes("grid") ||
    normalizedSection.includes("rete") ||
    normalizedSection.includes("ac") ||
    normalizedSection.includes("phase")
  ) {
    return "ac_grid";
  }

  if (
    normalizedSection.includes("dc") ||
    normalizedSection.includes("input") ||
    normalizedSection.includes("fv") ||
    normalizedSection.includes("solar") ||
    normalizedSection.includes("accumulo") ||
    normalizedSection.includes("battery") ||
    normalizedSection.includes("pack")
  ) {
    return "dc_storage";
  }

  if (
    normalizedSection.includes("status") ||
    normalizedSection.includes("alarm") ||
    normalizedSection.includes("fault") ||
    normalizedSection.includes("warning") ||
    normalizedSection.includes("stato") ||
    normalizedSection.includes("control") ||
    normalizedSection.includes("command") ||
    normalizedSection.includes("digital") ||
    normalizedSection.includes("relay") ||
    normalizedSection.includes("prote")
  ) {
    return "status_control";
  }

  if (
    normalizedSection.includes("identification") ||
    normalizedSection.includes("device") ||
    normalizedSection.includes("firmware") ||
    normalizedSection.includes("version") ||
    normalizedSection.includes("configurazione") ||
    normalizedSection.includes("sunspec") ||
    normalizedSection.includes("targa") ||
    normalizedSection.includes("error") ||
    normalizedSection.includes("diagnost")
  ) {
    return "identity_service";
  }

  return "other";
}

export function buildOrderedTelemetrySections(
  points: DeviceOverviewTelemetryPoint[],
): TelemetrySection[] {
  const grouped = new Map<string, DeviceOverviewTelemetryPoint[]>();

  points
    .filter((point) => point.visible)
    .forEach((point) => {
      const section = point.section || "General";
      const currentSection = grouped.get(section) ?? [];
      currentSection.push(point);
      grouped.set(section, currentSection);
    });

  return Array.from(grouped.entries())
    .map(([section, sectionPoints]) => ({
      section,
      points: [...sectionPoints].sort((left, right) => {
        const priorityDelta = pointPriority(left) - pointPriority(right);
        if (priorityDelta !== 0) {
          return priorityDelta;
        }

        return left.label.localeCompare(right.label, "it", { sensitivity: "base" });
      }),
    }))
    .sort((left, right) => {
      const priorityDelta = sectionPriority(left.section) - sectionPriority(right.section);
      if (priorityDelta !== 0) {
        return priorityDelta;
      }

      return left.section.localeCompare(right.section, "it", { sensitivity: "base" });
    });
}

export function buildTelemetryMacroGroups(
  points: DeviceOverviewTelemetryPoint[],
): TelemetryMacroGroup[] {
  const orderedSections = buildOrderedTelemetrySections(points);
  const groupedSections = new Map<string, TelemetrySection[]>();

  orderedSections.forEach((section) => {
    const macroKey = resolveTelemetryMacroGroupKey(section.section);
    const currentSections = groupedSections.get(macroKey) ?? [];
    currentSections.push(section);
    groupedSections.set(macroKey, currentSections);
  });

  return telemetryMacroGroupDefinitions
    .map((definition) => {
      const sections = groupedSections.get(definition.key) ?? [];
      if (sections.length === 0) {
        return null;
      }

      return {
        key: definition.key,
        title: definition.title,
        note: definition.note,
        sections,
        pointCount: sections.reduce((total, section) => total + section.points.length, 0),
      } satisfies TelemetryMacroGroup;
    })
    .filter((group): group is TelemetryMacroGroup => group !== null);
}

export function translateTelemetrySection(section: string): string {
  return sectionTranslations[normalize(section)] ?? section;
}

export function translateTelemetryLabel(label: string): string {
  const exact = exactLabelTranslations[label];
  if (exact) {
    return exact;
  }

  let translated = label;
  for (const [search, replacement] of labelReplacements) {
    translated = replaceInsensitive(translated, search, replacement);
  }

  return translated;
}

export function buildTelemetrySectionNote(section: string): string {
  const normalizedSection = normalize(section);

  if (
    normalizedSection.includes("produzione") ||
    normalizedSection.includes("production") ||
    normalizedSection.includes("power") ||
    normalizedSection.includes("misure inverter") ||
    normalizedSection.includes("misure der ac")
  ) {
    return "Priorita alla resa istantanea e agli indicatori di conversione.";
  }

  if (normalizedSection.includes("capacita der")) {
    return "Rating nominali e capacita operative dichiarate dal dispositivo.";
  }

  if (
    normalizedSection.includes("mains") ||
    normalizedSection.includes("grid") ||
    normalizedSection.includes("rete")
  ) {
    return "Valori lato rete utili a stabilita, tensioni e frequenza.";
  }

  if (normalizedSection.includes("dc")) {
    return "Quadro lato DC per tensioni, bus e condizioni di ingresso.";
  }

  if (
    normalizedSection.includes("thermal") ||
    normalizedSection.includes("temper")
  ) {
    return "Indicatori termici e di carico, utili per prevenzione e derating.";
  }

  if (
    normalizedSection.includes("status") ||
    normalizedSection.includes("alarm") ||
    normalizedSection.includes("fault") ||
    normalizedSection.includes("stati inverter") ||
    normalizedSection.includes("heartbeat")
  ) {
    return "Stato macchina e segnalazioni da tenere in primo piano in esercizio.";
  }

  if (normalizedSection.includes("accumulo")) {
    return "Stato, potenza e disponibilita dell'accumulo collegato all'inverter.";
  }

  if (normalizedSection.includes("control") || normalizedSection.includes("command")) {
    return "Setpoint e riferimenti operativi esposti dal modello.";
  }

  if (normalizedSection.includes("counter") || normalizedSection.includes("energy")) {
    return "Contatori cumulati e grandezze di bilancio energetico.";
  }

  if (
    normalizedSection.includes("dettagli inverter") ||
    normalizedSection.includes("versione mappa")
  ) {
    return "Identificativi, versioni e metadati utili a censimento e supporto tecnico.";
  }

  return "Telemetria esposta dinamicamente dal modello selezionato.";
}
