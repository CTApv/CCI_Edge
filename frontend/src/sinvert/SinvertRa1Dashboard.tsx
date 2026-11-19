import { useCallback, useEffect, useRef, useState } from "react";
import { getDevices, getDeviceOverview, runRa1Lab, saveRa1Settings, ra1TraceUrl,
  type Device, type DeviceOverview, type Ra1LabResult } from "../api";
import { SinvertRa1LabPanel } from "../components/SinvertRa1LabPanel";
import { Icon, Badge, Metric } from "./SinvertDashboard";
import { sinvertDeviceUrl } from "./routing";
import { number, timestamp } from "./presentation";
import { ra1View } from "./ra1Presentation";

const tabs = [
  { key: "overview", label: "Panoramica", icon: "grid" }, { key: "alarms", label: "Allarmi e avvisi", icon: "alert" },
  { key: "diagnostics", label: "Diagnostica", icon: "chip" }, { key: "commissioning", label: "Collaudo", icon: "settings" },
];

export function SinvertRa1Dashboard({ deviceId }: { deviceId: string }) {
  const [overview, setOverview] = useState<DeviceOverview | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [tab, setTab] = useState(() => {
    const q = new URLSearchParams(window.location.search).get("tab");
    return tabs.some(t => t.key === q) ? q! : "overview";
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Ra1LabResult | null>(null);
  const [resultAt, setResultAt] = useState("");
  const [actionError, setActionError] = useState("");
  const [scope, setScope] = useState(false);
  const [bench, setBench] = useState(false);
  const [limit, setLimit] = useState("");
  const [settingsMessage, setSettingsMessage] = useState("");
  const [groupIndex, setGroupIndex] = useState(1);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const mounted = useRef(true);
  const pending = useRef(false);
  const actionPending = useRef(false);
  const refresh = useCallback(async () => {
    if (pending.current) return;
    pending.current = true;
    try {
      const next = await getDeviceOverview(deviceId);
      if (next.device.brand !== "SINVERT RA1") throw new Error("Il dispositivo non usa più il profilo RA1. Riaprire la dashboard dal catalogo.");
      if (mounted.current) { setOverview(next); setError(""); }
    } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : "Dati non disponibili."); }
    finally { pending.current = false; }
  }, [deviceId]);
  useEffect(() => {
    mounted.current = true; void refresh();
    getDevices().then(list => { if (mounted.current) setDevices(list.filter(d => d.protocol === "s7_tcp" && ["SINVERT", "SINVERT RA1"].includes(d.brand))); }).catch(() => {});
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => { mounted.current = false; window.clearInterval(timer); };
  }, [refresh]);
  useEffect(() => { window.history.replaceState(null, "", sinvertDeviceUrl(deviceId) + (tab === "overview" ? "" : `&tab=${tab}`)); }, [tab, deviceId]);
  const model = ra1View(overview, Boolean(error));
  const { fresh, groups, messages, monitor } = model;
  const device = overview?.device;
  const enabled = device?.connection_settings.ra1_write_mode === "commissioning";
  const maximum = Number(device?.connection_settings.ra1_reference_max_raw ?? 0);
  const configured = groups.filter(g => g.configured === true);
  const alarms = messages.filter(m => m.kind === "alarm");
  const group = groups.find(g => g.index === groupIndex)!;
  const writable = enabled && fresh && !busy;
  const filtered = messages.filter(m => (filter === "all" || m.kind === filter) && `${m.address} gruppo ${m.group} bit ${m.bit}`.toLowerCase().includes(search.toLowerCase()));
  useEffect(() => { setLimit(String(maximum)); }, [maximum]);

  async function settings(nextEnabled: boolean, nextMaximum: number) {
    if (actionPending.current) return;
    actionPending.current = true; setBusy(true); setSettingsMessage("");
    try {
      if (!Number.isFinite(nextMaximum) || nextMaximum < 0 || nextMaximum > 1000000) throw new Error("Limite ammesso: 0..1000000. Con 0 il riferimento è disabilitato.");
      const updated = await saveRa1Settings(deviceId, nextEnabled, nextMaximum);
      setOverview(current => current ? { ...current, device: updated } : current);
      setSettingsMessage("Impostazioni salvate nell’app. Nessun comando PLC inviato.");
      await refresh();
    } catch (e) { setSettingsMessage(e instanceof Error ? e.message : "Salvataggio non riuscito."); }
    finally { actionPending.current = false; setBusy(false); }
  }
  async function command(key: string, value = 1, dryRun = true) {
    if (actionPending.current) return;
    actionPending.current = true; setBusy(true); setActionError(""); setResult(null);
    try {
      const next = await runRa1Lab(deviceId, "command", { command: key, value, dry_run: dryRun, enabled, bench, scope_confirmed: scope });
      if (mounted.current) { setResult(next); setResultAt(new Date().toISOString()); }
      await refresh();
    } catch (e) { setActionError(e instanceof Error ? e.message : "Esito non disponibile: controllare prima di ripetere."); }
    finally { actionPending.current = false; setBusy(false); }
  }
  const actionButtons = (key: string, label: string, value = 1) => <div className="sv-ra1-actions">
    <button className="sv-button sv-button--white" disabled={busy || !fresh} onClick={() => void command(key, value)}>Verifica {label}</button>
    <button className={`sv-button ${key === "off" ? "sv-button--stop" : "sv-button--primary"}`} disabled={!writable || !scope} onClick={() => void command(key, value, false)}>{label}</button>
  </div>;
  const controls = <section className="sv-panel">
    <div className="sv-panel-heading"><Icon name="settings"/><h2>Comandi manuali RA1</h2></div>
    <p>ON/OFF agiscono sull’intero PLC. I reset dei gruppi inviano un impulso al relativo comando AUTO/TEST; non certificano la scomparsa degli allarmi.</p>
    <label className="sv-toggle"><input type="checkbox" checked={scope} disabled={busy} onChange={e => setScope(e.target.checked)}/><span>Confermo l’ambito del comando e il controllo esclusivo del PLC.</span></label>
    <label className="sv-toggle"><input type="checkbox" checked={bench} disabled={busy} onChange={e => setBench(e.target.checked)}/><span>Banco con sola CPU e CP, senza inverter o periferiche. Le condizioni di isolamento vengono rilette a ogni comando.</span></label>
    <div className="sv-ra1-actions">{actionButtons("on", "ON collettivo")}{actionButtons("off", "OFF collettivo")}{actionButtons("reset_all", "Reset gruppi configurati")}</div>
    <div className="sv-table-scroll"><table><thead><tr><th>Gruppo</th><th>Selettore</th><th>AUTO / TEST</th><th>Pulsante operatore</th><th>Reset</th></tr></thead><tbody>{groups.map(g => <tr key={g.index}><td>Gruppo {g.index}{g.configured === false ? " · non configurato" : ""}</td><td>{!fresh || g.test == null ? "—" : g.test ? "TEST" : "AUTO"}</td><td>{g.configured === true && <>{actionButtons(`group_${g.index}_test`, "AUTO", 0)}{actionButtons(`group_${g.index}_test`, "TEST", 1)}</>}</td><td>{g.configured === true && actionButtons(`group_${g.index}_operator`, "Impulso operatore")}</td><td>{g.configured === true && actionButtons(`group_${g.index}_reset`, "Reset gruppo")}</td></tr>)}</tbody></table></div>
    <p className="sv-source-note">OFF chiude prima la sessione CP del dispositivo e resta pendente finché il PLC lo elabora. Non vengono forzati consensi o abilitazioni. Il reset generale usa i gruppi configurati; non scrive il bit ACK non identificato della vecchia variante.</p>
  </section>;

  return <div className="sv-shell sv-ra1">
    <aside className="sv-sidebar">
      <a className="sv-brand" href="/"><picture><source media="(max-width: 1050px)" srcSet="/favicon_cta.png"/><img src="/logo_HBA_STE.png" alt="HBA e STE"/></picture><span>PV Guardian<small>Supervisione fotovoltaica</small></span></a>
      <div className="sv-workspace-label">DISPOSITIVO <span>SINVERT RA1</span></div>
      <nav aria-label="Navigazione SINVERT RA1">{tabs.map(t => <button key={t.key} className={tab === t.key ? "active" : ""} aria-current={tab === t.key ? "page" : undefined} onClick={() => setTab(t.key)}><Icon name={t.icon}/>{t.label}{t.key === "alarms" && alarms.length > 0 && <em>{alarms.length}</em>}</button>)}</nav>
      <div className="sv-sidebar-divider"/><p className="sv-nav-caption">CONNESSIONE SELEZIONATA</p>
      <div className="sv-plc-tile"><Icon name="chip"/><div><strong>PLC SINVERT RA1</strong><span>{String(device?.connection_settings.host ?? "In attesa")}</span></div><i className={`sv-dot sv-dot--${fresh ? "ok" : "muted"}`}/></div>
      <div className="sv-sidebar-bottom"><div><Icon name="lock" size={16}/><span>Controllo e diagnostica</span></div><p>Progetto 420 · collaudo dedicato.</p><a href="/">Torna alla dashboard <Icon name="arrow" size={16}/></a></div>
    </aside>
    <div className="sv-workspace"><header className="sv-topbar"><div><a className="sv-breadcrumb" href="/">PV Guardian</a><span>/</span><strong>SINVERT RA1</strong><span className="sv-preview">Collaudo progetto 420</span></div><span className="sv-live"><i className={`sv-dot sv-dot--${fresh ? "ok" : "muted"}`}/>{fresh ? "Dati dal PLC" : "Dati da verificare"}</span></header>
      <main className="sv-main">
        <div className="sv-page-heading"><div><p className="sv-eyebrow">SUPERVISIONE E CONTROLLO</p><h1>{device?.name ?? "SINVERT RA1"}</h1><p>420 S7-300 · KOMM 3.0 / REGEL 3.9</p></div><div className="sv-page-actions"><select aria-label="Seleziona PLC SINVERT" value={deviceId} onChange={e => window.location.assign(sinvertDeviceUrl(e.target.value))}>{devices.length ? devices.map(d => <option key={d.device_id} value={d.device_id}>{d.name} · {d.brand}</option>) : <option value={deviceId}>SINVERT RA1</option>}</select><button className="sv-button sv-button--white" onClick={() => void refresh()}><Icon name="refresh"/>Aggiorna</button><a className="sv-button sv-button--white" href={ra1TraceUrl(deviceId)}><Icon name="chip"/>Esporta traccia</a></div></div>
        {error && <div className="sv-notice sv-notice--bad" role="alert"><Icon name="alert"/><p>{error}</p></div>}
        {!overview ? <div className="sv-empty">Acquisizione del PLC RA1…</div> : <>
          <div className="sv-status-strip"><Badge tone={fresh ? "ok" : "warn"}>{fresh ? "Collegato" : "Dati da verificare"}</Badge><span>{enabled ? "Collaudo abilitato nell’app" : "Sola lettura"}</span><span>Ultimo campione: {timestamp(overview.diagnostics.last_valid_data_at)}</span></div>
          {tab === "overview" && <>
            <div className="sv-kpis"><Metric label="Gruppi configurati" value={String(configured.length)} note="Quattro gruppi esposti dal progetto" icon="inverter"/><Metric label="Disponibilità PLC" value={fresh ? String(configured.filter(g => g.consent).length) : "—"} note="Segnali M55 · nessun riscontro fisico indipendente" icon="link"/><Metric label="Bit di allarme" value={fresh && configured.every(g => g.complete) ? String(alarms.length) : "—"} note="Finestre allarmi dei gruppi configurati" icon="alert"/><Metric label="Riferimento A" value={fresh ? number(monitor?.reference_a) : "—"} note="Valore PLC grezzo · scala da confermare" icon="bolt"/></div>
            <div className="sv-overview-layout"><section><div className="sv-section-title"><div><h2>Gruppi inverter</h2><p>Master e slave sono rappresentati nei gruppi gestiti dal PLC.</p></div><Badge tone="muted">{configured.length} gruppi</Badge></div><div className="sv-inverter-grid">{groups.map(g => <article key={g.index} className={`sv-inverter ${g.configured === false ? "sv-inverter--unused" : ""}`}><div className="sv-inverter-head"><span className="sv-device-icon"><Icon name="inverter" size={25}/></span><div><h3>Gruppo {String(g.index).padStart(2,"0")}</h3><span>{g.configured == null ? "Configurazione non nota" : g.configured ? "Configurato nel PLC" : "Non configurato"}</span></div></div><div className="sv-inverter-statusline"><Badge tone={!fresh ? "muted" : g.consent ? "ok" : "warn"}>{!fresh ? "Campione non aggiornato" : g.configured === false ? "Non utilizzato" : `Stato PLC ${g.state ?? "—"}`}</Badge></div><div className="sv-inverter-power"><span>Potenza attiva · valore PLC grezzo</span><strong>{fresh && g.configured ? number(g.active) : "—"}</strong></div><div className="sv-mini-metrics"><div><span>Tensione DC grezza</span><b>{fresh && g.configured ? number(g.dcVoltage) : "—"}</b></div><div><span>Corrente DC grezza</span><b>{fresh && g.configured ? number(g.dcCurrent) : "—"}</b></div></div><div className="sv-inverter-foot"><span>{!fresh ? "Dati da verificare" : g.consent ? "Consenso M55 presente" : "Consenso non presente"}</span><button aria-label={`Diagnostica gruppo ${g.index}`} onClick={() => { setGroupIndex(g.index); setTab("diagnostics"); }}><Icon name="arrow"/></button></div></article>)}</div></section><aside className="sv-control-column"><section className="sv-panel"><div className="sv-panel-heading"><Icon name="settings"/><h2>Controllo collettivo</h2></div><p>I comandi agiscono su tutte le posizioni del PLC.</p><label className="sv-toggle"><input type="checkbox" checked={scope} disabled={busy} onChange={e => setScope(e.target.checked)}/><span>Confermo comando collettivo e controllo esclusivo.</span></label>{bench && <Badge tone="warn">Banco CPU/CP dichiarato</Badge>}{actionButtons("on", "ON collettivo")}{actionButtons("off", "OFF collettivo")}<button className="sv-text-button" onClick={() => setTab("commissioning")}>Apri impostazioni e reset <Icon name="arrow"/></button></section><section className="sv-panel sv-power-panel"><h2>Riferimento del regolatore</h2><Badge tone="warn">Scala da validare</Badge><p>Ricevuto: {fresh ? number(monitor?.reference_a) : "—"}</p><p>Ingresso: {fresh ? number(monitor?.regulator_a) : "—"}</p><p>Dopo selezione/rampa: {fresh ? number(monitor?.processed_a) : "—"}</p><button className="sv-text-button" onClick={() => setTab("commissioning")}>Apri collaudo del riferimento <Icon name="arrow"/></button></section></aside></div>
          </>}
          {tab === "alarms" && <section className="sv-panel sv-table-panel"><div className="sv-section-title"><div><h2>Allarmi e avvisi del PLC</h2><p>128 bit per tipo e gruppo. Descrizioni specifiche RA1 da validare.</p></div><Badge tone={fresh ? "muted" : "warn"}>{fresh ? "Campione corrente" : "Campione non aggiornato"}</Badge></div><div className="sv-table-tools"><select aria-label="Tipo messaggio" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">Tutti</option><option value="alarm">Allarmi</option><option value="warning">Avvisi</option></select><input aria-label="Cerca messaggio RA1" placeholder="Cerca gruppo, bit o indirizzo" value={search} onChange={e => setSearch(e.target.value)}/></div><div className="sv-table-scroll"><table><thead><tr><th>Tipo</th><th>Gruppo</th><th>Bit PLC</th><th>Indirizzo</th></tr></thead><tbody>{filtered.map(m => <tr key={`${m.group}-${m.kind}-${m.address}`}><td><Badge tone={m.kind === "alarm" ? "bad" : "warn"}>{m.kind === "alarm" ? "Allarme" : "Avviso"}</Badge></td><td>{m.group}</td><td>{m.bit}</td><td><code>{m.address}</code></td></tr>)}</tbody></table></div>{!filtered.length && <div className="sv-empty">Nessun bit attivo nel filtro del campione. Completezza finestre: {configured.every(g => g.complete) ? "confermata" : "non confermata"}.</div>}</section>}
          {tab === "diagnostics" && <div className="sv-diagnostic-layout"><section className="sv-panel"><div className="sv-section-title"><h2>Origine dei segnali</h2><select aria-label="Gruppo da analizzare" value={groupIndex} onChange={e => setGroupIndex(Number(e.target.value))}>{groups.map(g => <option key={g.index} value={g.index}>Gruppo {g.index}</option>)}</select></div><dl className="sv-definition-list"><div><dt>Stato PLC grezzo</dt><dd>{group.state ?? "—"}</dd></div><div><dt>Disponibilità M55</dt><dd>{group.consent == null ? "Dato assente" : group.consent ? "Presente" : "Assente"}</dd></div><div><dt>Selettore AUTO/TEST</dt><dd>{group.test == null ? "Dato assente" : group.test ? "TEST" : "AUTO"}</dd></div><div><dt>Firma programma acquisizione</dt><dd>{monitor?.program_verified ? "Riconosciuta" : "Da verificare"}</dd></div><div><dt>Ramo CP</dt><dd>{monitor?.cp_enabled == null ? "Dato assente" : monitor.cp_enabled ? "Abilitato nel PLC" : "Disabilitato nel PLC"}</dd></div><div><dt>Parametri CP</dt><dd>{monitor?.cp_parameters_match ? "Conformi al progetto" : "Da verificare"}</dd></div><div><dt>Feedback fisico dei comandi</dt><dd>Non confermato</dd></div></dl><ul className="sv-technical-reasons">{monitor?.blockers.map(b => <li key={b}>{b}</li>)}</ul></section><section className="sv-panel"><h2>Telemetria e qualità</h2><p>{overview.telemetry.length} punti · {overview.diagnostics.failed_points} letture non riuscite.</p><div className="sv-table-scroll sv-raw-table"><table><thead><tr><th>Segnale</th><th>Raw</th><th>Qualità</th></tr></thead><tbody>{overview.telemetry.map(p => <tr key={p.key}><td>{p.label}</td><td><code>{String(p.raw_value ?? "—")}</code></td><td>{p.quality}</td></tr>)}</tbody></table></div></section></div>}
          {tab === "commissioning" && <>
            <section className="sv-panel"><h2>Impostazioni del collaudo</h2><label className="sv-toggle"><input type="checkbox" checked={enabled} disabled={busy} onChange={e => void settings(e.target.checked, maximum)}/><span>Abilita il collaudo manuale RA1 nell’app. Il salvataggio non modifica il PLC.</span></label><div className="sv-reference-form"><label>Massimo riferimento grezzo consentito<input type="number" min="0" max="1000000" step="any" value={limit} disabled={busy} onChange={e => setLimit(e.target.value)}/></label><button className="sv-button sv-button--white" disabled={busy || !limit.trim()} onClick={() => void settings(enabled, Number(limit))}>Salva limite nell’app</button></div><p>Con 0 l’invio del riferimento è disabilitato. Il limite non è una potenza nominale.</p>{settingsMessage && <p role="status">{settingsMessage}</p>}</section>
            {controls}
            <section className="sv-panel"><h2>Catena del riferimento A</h2><p>Valori correnti in unit? PLC grezze. La ricezione CP diretta usa DB944; DB511 ? il buffer HMI alternativo.</p><div className="sv-table-scroll"><table><thead><tr><th>Buffer HMI alternativo</th><th>Ricevuto CP</th><th>Ingresso regolatore</th><th>Dopo selezione/rampa</th></tr></thead><tbody><tr><td>{fresh ? number(model.value("ra1_hmi_reference_a")) : "?"}</td><td>{fresh ? number(monitor?.reference_a) : "?"}</td><td>{fresh ? number(monitor?.regulator_a) : "?"}</td><td>{fresh ? number(monitor?.processed_a) : "?"}</td></tr></tbody></table></div></section>
            <SinvertRa1LabPanel deviceId={deviceId} enabled={enabled} referenceLimit={maximum}/>
          </>}
          {(result || actionError) && <section className="sv-panel sv-outcome" aria-live="polite"><div className="sv-panel-heading"><h2>Ultima operazione</h2><span>{timestamp(resultAt)}</span></div>{actionError ? <p role="alert">{actionError}</p> : result && <><Badge tone={result.success ? "ok" : "warn"}>{result.success ? "Controlli completati" : "Operazione non confermata"}</Badge><p>{result.stage === "preflight_passed" ? "Verifica in sola lettura: nessun comando inviato." : result.error ?? "Richiesta inviata al PLC. Verificare l’esito e il riscontro fisico."}</p><div className="sv-result-steps"><span className={result.write_accepted ? "done" : ""}>Accettazione S7: {result.write_accepted ? "confermata" : "non confermata"}</span><Icon name="arrow"/><span>Elaborazione PLC: {result.plc_processed ? "richiesta consumata" : "non confermata"}</span><Icon name="arrow"/><span>Riscontro fisico: non confermato</span></div><details className="sv-details"><summary>Dettagli tecnici dell’esito</summary><pre>{JSON.stringify(result, null, 2)}</pre></details></>}</section>}
        </>}
        <footer className="sv-footer"><span>PV Guardian · SINVERT RA1</span><span>Collaudo progetto 420 · riscontro fisico da validare</span><span>{timestamp(overview?.diagnostics.last_valid_data_at)}</span></footer>
      </main>
    </div>
    <nav className="sv-mobile-nav" aria-label="Navigazione mobile RA1">{tabs.map(t => <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}><Icon name={t.icon}/>{t.label}</button>)}</nav>
    {busy && <div className="sv-working" role="status"><Icon name="refresh"/>Controlli in corso…</div>}
  </div>;
}
