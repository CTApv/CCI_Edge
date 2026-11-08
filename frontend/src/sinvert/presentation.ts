import type { DeviceOverview, SinvertMonitor } from "../api";

export type Group = SinvertMonitor["groups"][number];
export type Tone = "ok" | "warn" | "bad" | "muted";
export type Tab = "overview" | "alarms" | "commissioning" | "diagnostics";

export const commandNames: Record<string, string> = {
  sinvert_alarm_ack: "Reset allarmi · riconoscimento collettivo",
  sinvert_on_request: "Richiesta ON collettiva · M34.2", sinvert_off_request: "Richiesta OFF collettiva · M34.3",
  sinvert_power_reference_raw: "Riferimento di potenza",
};
for (let unit=1; unit<=4; unit++) {
  commandNames[`sinvert_unit_${unit}_reset`] = `INV${unit}: Reset · DB402.${842+194*(unit-1)}.1`;
  commandNames[`sinvert_unit_${unit}_test_mode`] = `INV${unit}: selettore AUTO/TEST · DB402.${842+194*(unit-1)}.1`;
  commandNames[`sinvert_unit_${unit}_operator_pulse`] = `INV${unit}: pulsante operatore · DB402.${842+194*(unit-1)}.0`;
}
export const number = (value: number | null | undefined, digits = 1) =>
  value == null || !Number.isFinite(value) ? "—" : new Intl.NumberFormat("it-IT", { maximumFractionDigits: digits, useGrouping: true }).format(value);
export function timestamp(value?: string | null) {
  if (!value || Number.isNaN(new Date(value).getTime())) return "Non disponibile";
  return new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value));
}
export function groupState(group: Group, fresh: boolean): { label: string; detail: string; tone: Tone } {
  if (group.configured === false) return { label: "Non configurato", detail: "Posizione non utilizzata dal PLC", tone: "muted" };
  if (!fresh) return { label: "Stato non aggiornato", detail: "In attesa di un nuovo campione", tone: "muted" };
  if (group.measurement_quality === "communication_flags") return { label: "Feedback da verificare", detail: "Il PLC segnala condizioni di comunicazione non valide", tone: "warn" };
  if (group.measurement_quality !== "plc_reported") return { label: "Stato non confermato", detail: "I dati non consentono di determinare lo stato", tone: "muted" };
  if (![1,2,3,4].includes(group.state_code ?? -1)) return { label: "Stato non riconosciuto", detail: "Codice da verificare nella variante del programma", tone: "muted" };
  if (group.state_code === 4) return { label: "Allarmi presenti", detail: "Stato riportato dal PLC", tone: "bad" };
  if (group.state_code === 3) return { label: "Avvisi presenti", detail: "Stato riportato dal PLC", tone: "warn" };
  if (group.state_code === 2) return { label: "In marcia · PLC", detail: "Indicazione PLC; riscontro fisico da validare", tone: "ok" };
  return { label: "Non in marcia · PLC", detail: "Indicazione PLC; riscontro fisico da validare", tone: "muted" };
}
export function explainBlocker(value: string) {
  if (value.includes("M55")) return "Nessun gruppo è disponibile al controllo. Il PLC mantiene la richiesta di arresto.";
  if (value.includes("M/TL")) return "La modalità di controllo prevista non è confermata.";
  if (value.includes("M34") || value.includes("Sequenza DB64")) return "Il PLC sta gestendo una richiesta o una sequenza precedente.";
  if (value.includes("M0.4") || value.includes("M23.1")) return "È in corso una reinizializzazione del PLC, oppure il suo stato non è leggibile.";
  if (value.includes("Copia esterna")) return "Il canale del riferimento esterno non è abilitato completamente.";
  if (value.includes("DB3.0.7")) return "Manca l'abilitazione esterna prevista dal PLC.";
  if (value.includes("Watchdog")) return "Il collegamento con il controllore esterno non è confermato dal watchdog.";
  if (value.includes("Errore canale")) return "Il PLC segnala un errore sul canale del riferimento esterno.";
  if (value.includes("Limite del riferimento")) return "Il limite locale per il collaudo del riferimento non è configurato.";
  if (value.includes("incompleta")) return "Non tutti i segnali necessari sono disponibili.";
  return value;
}
export function summary(overview: DeviceOverview | null, failed: boolean) {
  const monitor = overview?.diagnostics.sinvert;
  const fresh = !failed && overview?.diagnostics.data_freshness === "fresh"
    && overview.diagnostics.communication_state === "online";
  const configured = monitor?.groups.filter(group => group.configured === true) ?? [];
  const reporting = configured.filter(group => group.measurement_quality === "plc_reported");
  const alarms = configured.flatMap(group => group.active_messages.filter(message => message.kind === "alarm"));
  const allMeasurements = fresh && configured.length > 0 && reporting.length === configured.length;
  const power = allMeasurements && reporting.every(group => group.measurements.active_power != null && Number.isFinite(group.measurements.active_power))
    ? reporting.reduce((total, group) => total + group.measurements.active_power!, 0) : null;
  return { monitor, fresh, configured, reporting, alarms, power };
}
