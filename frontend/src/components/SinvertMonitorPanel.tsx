import { useState } from "react";
import { checkSinvertCommand, saveSinvertReferenceLimit, type DeviceOverview, type CommandResponse } from "../api";

const format = (value: number | null | undefined, unit = "") =>
  value == null ? "--" : `${new Intl.NumberFormat("it-IT", { maximumFractionDigits: 2 }).format(value)} ${unit}`.trim();
const yesNo = (value: boolean | null) => value === null ? "Dato assente" : value ? "Sì" : "No";

export function SinvertMonitorPanel({ overview, onSettingsSaved }: { overview: DeviceOverview; onSettingsSaved?: () => void }) {
  const monitor = overview.diagnostics.sinvert;
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<CommandResponse | null>(null);
  const [error, setError] = useState("");
  const [raw, setRaw] = useState("0");
  const [maximum, setMaximum] = useState(String(overview.device.connection_settings.sinvert_reference_max_raw ?? 0));
  const [saving, setSaving] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState("");
  if (!monitor) return null;
  const fresh = overview.diagnostics.data_freshness === "fresh";
  async function saveMaximum() {
    setSettingsMessage("");
    const value = Number(maximum);
    if (!maximum.trim() || !Number.isFinite(value) || value < 0 || value > 1000000) {
      setSettingsMessage("Inserire un limite PLC tra 0 e 1000000; 0 disabilita l’invio del riferimento."); return;
    }
    setSaving(true);
    try {
      await saveSinvertReferenceLimit(overview.device.device_id, value);
      setSettingsMessage(value > 0 ? `Limite locale salvato: ${value}. L’invio richiede ancora tutti i consensi PLC; nessun comando inviato.` : "Invio riferimento disabilitato. Nessun comando inviato.");
      onSettingsSaved?.();
    } catch (e) { setSettingsMessage(e instanceof Error ? e.message : "Salvataggio non riuscito"); }
    finally { setSaving(false); }
  }
  async function check(key: string) {
    setChecking(true); setError(""); setResult(null);
    try {
      const value = key === "sinvert_power_reference_raw" ? Number(raw) : 1;
      if (!Number.isFinite(value) || (key === "sinvert_power_reference_raw" && !raw.trim())) throw new Error("Inserire un valore PLC finito.");
      setResult(await checkSinvertCommand(overview.device.device_id, key, value));
    } catch (e) { setError(e instanceof Error ? e.message : "Verifica non disponibile"); }
    finally { setChecking(false); }
  }
  return <section className="detail-section">
    <h3>Monitoraggio SINVERT e consensi</h3>
    <p className="detail-copy">{fresh ? "Ultima acquisizione PLC" : "Dati non aggiornati: non usarli come consenso operativo"}. Collegamento al PLC e comunicazione con gli inverter sono distinti.</p>
    <div className="detail-grid">
      {monitor.groups.map((group) => <article key={group.index} className="detail-card">
        <h4>INV{group.index} — {group.configured === false ? "Non configurato" : group.state_label}</h4>
        <p>Codice stato: {group.state_code ?? "--"} · Consenso M55: {yesNo(group.consent)}</p>
        <p>ON HMI: {yesNo(group.hmi_on)} · Contattore AC HMI: {yesNo(group.hmi_ac_contactor)}</p>
        <p>Entrambi derivano da M55: non sono due conferme indipendenti.</p>
        {group.consent_reasons.length > 0 && <ul>{group.consent_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
        <p>Qualità misure: {group.measurement_quality === "plc_reported" ? "Valori riportati dal PLC, riscontro fisico da validare" : group.measurement_quality}</p>
        <p>P: {fresh ? format(group.measurements.active_power, "kW") : "--"} · Q: {fresh ? format(group.measurements.reactive_power, "kvar") : "--"}</p>
        <p>AC L1: {fresh ? format(group.measurements.voltage_l1, "V") : "--"} · f: {fresh ? format(group.measurements.frequency, "Hz") : "--"}</p>
        <p>DC: {fresh ? format(group.measurements.dc_voltage, "V") : "--"} · {fresh ? format(group.measurements.dc_current, "A") : "--"}</p>
        <details><summary>Messaggi attivi: {group.active_messages.length}{group.messages_complete ? "" : " (lettura incompleta)"}</summary>
          <p>Descrizioni dal manuale V1.0, da verificare nella variante PLC. Per gruppi non configurati i bit possono essere residui.</p>
          <ul>{group.active_messages.map((message) => <li key={message.address}>{message.address} — {message.kind === "alarm" ? "Allarme" : "Avviso"}: {message.label}{message.manual_page ? ` (p.${message.manual_page})` : ""}</li>)}</ul>
        </details>
      </article>)}
    </div>
    <h4>Avvio e regolazione</h4>
    <p>Collaudo manuale: {monitor.manual_enabled ? "abilitato" : "disabilitato"}. Ambito comandi: intero PLC.</p>
    <p>{monitor.on_blockers.length ? "Blocchi ON rilevati:" : "Nessun blocco ON rilevato nel campione; programma e consensi saranno ricontrollati all’invio."}</p>
    <ul>{monitor.on_blockers.map((reason) => <li key={reason}>{reason}</li>)}</ul>
    <p>Blocchi riferimento di potenza:</p>
    <ul>{monitor.power_blockers.map((reason) => <li key={reason}>{reason}</li>)}</ul>
    <p>Riferimento A — esterno: {format(monitor.reference_chain.controller_a_external_raw)} → copiato: {format(monitor.reference_chain.controller_a_copied_raw)} → ingresso regolatore: {format(monitor.reference_chain.controller_a_input_raw)}.</p>
    <p>Dopo selezione/rampa: {format(monitor.reference_chain.controller_a_processed_raw)} · fallback configurato: {format(monitor.reference_chain.controller_fallback_a)}. L’ingresso ricevuto può essere sostituito dal fallback.</p>
    <p>Valori PLC grezzi: unità del comando e modulazione fisica da validare. Nessuna conversione automatica in percentuale.</p>
    {overview.device.model.includes("Collaudo comandi") && <div>
      <h4>Limite per l’invio del riferimento grezzo</h4>
      <p>Limite attuale: {String(overview.device.connection_settings.sinvert_reference_max_raw ?? 0)}. Con 0 l’invio è disabilitato. Usare la scala PLC concordata per il collaudo, non una percentuale presunta.</p>
      <label className="field"><span className="field-label">Massimo valore PLC consentito</span>
        <input className="field-control" type="number" min="0" max="1000000" step="any" value={maximum} disabled={saving} onChange={(e) => setMaximum(e.target.value)} />
      </label>
      <button className="secondary-button" type="button" disabled={saving} onClick={() => void saveMaximum()}>{saving ? "Salvataggio…" : "Salva limite locale senza inviare"}</button>
      {settingsMessage && <p role="status">{settingsMessage}</p>}
    </div>}
    <h4>Verifica preventiva — nessuna scrittura</h4>
    <div className="detail-grid">
      <button type="button" className="secondary-button" disabled={checking} onClick={() => void check("sinvert_on_request")}>Verifica ON senza inviare</button>
      <button type="button" className="secondary-button" disabled={checking} onClick={() => void check("sinvert_off_request")}>Verifica OFF senza inviare</button>
      <label>Riferimento PLC da verificare <input type="number" step="any" value={raw} onChange={(event) => setRaw(event.target.value)} /></label>
      <button type="button" className="secondary-button" disabled={checking} onClick={() => void check("sinvert_power_reference_raw")}>Verifica riferimento senza inviare</button>
    </div>
    {checking && <p>Verifica del programma e delle condizioni attuali del PLC…</p>}
    {result && <p role="status">Verifica {({ sinvert_on_request: "ON", sinvert_off_request: "OFF", sinvert_power_reference_raw: "riferimento di potenza" } as Record<string, string>)[result.command] ?? result.command} {result.success ? "superata" : "bloccata"}: {result.message}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
