import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { checkSinvertCommand, getDeviceOverview, getDevices, saveSinvertReferenceLimit, sendDeviceCommand,
  type Device, type DeviceOverview, type CommandResponse } from "../api";
import { commandNames, explainBlocker, groupState, number, summary, timestamp, type Group, type Tab, type Tone } from "./presentation";

function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
    bolt: <path d="m13 2-8 12h6l-1 8 9-13h-7z"/>,
    alert: <><path d="m10.3 4.1-8 14a2 2 0 0 0 1.7 3h16a2 2 0 0 0 1.7-3l-8-14a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4m0 4h.01"/></>,
    settings: <><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/></>,
    chip: <><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4"/><path d="M10 10h4v4h-4z"/></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.3 6.3A8 8 0 0 1 20 12M4 12a8 8 0 0 0 13.7 5.7"/></>,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5"/>,
    check: <path d="m5 12 4 4L19 6"/>,
    play: <path d="m8 4 12 8-12 8z"/>,
    stop: <rect x="5" y="5" width="14" height="14" rx="2"/>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/></>,
    link: <><path d="m10 13 4-4m-7 5-2 2a4 4 0 0 0 6 6l3-3m-4-9 3-3a4 4 0 0 1 6 6l-2 2"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    inverter: <><rect x="5" y="2" width="14" height="20" rx="2"/><path d="M8 6h8M8 10h8m-8 7c2-5 4 5 8 0"/></>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.grid}</svg>;
}
function Badge({ tone = "muted", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`sv-badge sv-badge--${tone}`}><i/>{children}</span>;
}
function Empty({ children }: { children: ReactNode }) { return <div className="sv-empty"><Icon name="chip" size={28}/><p>{children}</p></div>; }
function GroupCard({ group, fresh, select }: { group: Group; fresh: boolean; select: () => void }) {
  const state = groupState(group, fresh);
  const enabled = group.configured !== false;
  const valid = fresh && group.measurement_quality === "plc_reported";
  const alarms = group.active_messages.filter(message => message.kind === "alarm").length;
  return <article className={`sv-inverter ${enabled ? "" : "sv-inverter--unused"}`}>
    <div className="sv-inverter-head"><span className="sv-device-icon"><Icon name="inverter" size={25}/></span><div><h3>Inverter {String(group.index).padStart(2,"0")}</h3><span>Posizione {group.index} del PLC</span></div><span className={`sv-dot sv-dot--${state.tone}`}/></div>
    <div className="sv-inverter-statusline"><Badge tone={state.tone}>{state.label}</Badge>{fresh && enabled && alarms > 0 && <span className="sv-mini-alert"><Icon name="alert" size={12}/>{alarms} {alarms === 1 ? "allarme PLC" : "allarmi PLC"}</span>}</div>
    {enabled ? <><div className="sv-inverter-power"><span>Potenza attiva</span><strong>{number(valid ? group.measurements.active_power : null)} <small>kW</small></strong></div>
    <div className="sv-mini-metrics"><div><span>Potenza reattiva</span><b>{number(valid ? group.measurements.reactive_power : null)} <small>kvar</small></b></div><div><span>Frequenza</span><b>{number(valid ? group.measurements.frequency : null, 2)} <small>Hz</small></b></div></div></> : <p className="sv-unused-body">Nessuna misura attesa per questa posizione.</p>}
    <div className="sv-inverter-foot"><span>{!enabled ? "Escluso dal controllo" : !fresh ? "Dati non aggiornati" : group.consent ? "Segnale di disponibilità attivo" : "Disponibilità non confermata"}</span><button onClick={select} aria-label={`Apri diagnostica inverter ${group.index}`}><Icon name="arrow" size={17}/></button></div>
  </article>;
}

type Action = { key: string; value: number; deviceId: string };
type Outcome = { result: CommandResponse; at: string; kind: "check" | "send" };
const tabs: { key: Tab; label: string; icon: string }[] = [
  {key:"overview",label:"Panoramica",icon:"grid"}, {key:"alarms",label:"Allarmi e avvisi",icon:"alert"},
  {key:"commissioning",label:"Collaudo",icon:"settings"}, {key:"diagnostics",label:"Diagnostica",icon:"chip"},
];

export function SinvertDashboard() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [selected, setSelected] = useState("");
  const [overview, setOverview] = useState<DeviceOverview | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [manual, setManual] = useState(false);
  const [raw, setRaw] = useState("");
  const [limit, setLimit] = useState("");
  const [saving, setSaving] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [review, setReview] = useState<Action | null>(null);
  const [actionError, setActionError] = useState("");
  const [groupIndex, setGroupIndex] = useState(1);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const outcomeRef = useRef<HTMLElement | null>(null);
  const selectedRef = useRef(selected); selectedRef.current = selected;
  const fetchData = useCallback(async (id: string) => {
    if (!id || inFlight.current) return;
    inFlight.current = true;
    try {
      const data = await getDeviceOverview(id);
      if (mounted.current && selectedRef.current === id) { setOverview(data); setLoadError(""); }
    } catch (error) { if (mounted.current && selectedRef.current === id) setLoadError(error instanceof Error ? error.message : "Acquisizione non disponibile"); }
    finally { inFlight.current = false; if (mounted.current) setLoading(false); }
  }, []);
  useEffect(() => {
    mounted.current = true;
    getDevices().then(list => {
      if (!mounted.current) return;
      const found = list.filter(device => device.protocol === "s7_tcp" && device.brand === "SINVERT");
      setDevices(found); if (found.length) setSelected(found[0].device_id); else setLoading(false);
    }).catch(error => { if (mounted.current) { setLoadError(String(error)); setLoading(false); } });
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    if (!selected) return;
    setOverview(null); setManual(false); setReview(null); setOutcome(null); setLoading(true);
    void fetchData(selected);
    const timer = window.setInterval(() => void fetchData(selected), 5000);
    return () => window.clearInterval(timer);
  }, [selected, fetchData]);
  const model = summary(overview, Boolean(loadError));
  const { monitor, fresh, configured, reporting, alarms, power } = model;
  const device = overview?.device ?? devices.find(entry => entry.device_id === selected);
  const max = Number(device?.connection_settings.sinvert_reference_max_raw ?? 0);
  const commissioning = Boolean(device?.model.includes("Collaudo comandi"));
  const writable = fresh && commissioning && monitor?.manual_enabled === true && manual;
  const startBlocked = !monitor || monitor.on_blockers.length > 0;
  const connection = !overview ? "In attesa" : fresh ? "Collegato" : "Da verificare";
  const problems = [...new Set((monitor?.on_blockers ?? []).map(explainBlocker))];
  const messages = (monitor?.groups ?? []).filter(group => group.configured === true).flatMap(group => group.active_messages.map(message => ({ ...message, index: group.index, complete: group.messages_complete })));
  const filtered = messages.filter(message => (filter === "all" || message.kind === filter) && `${message.label} ${message.address} inverter ${message.index}`.toLowerCase().includes(search.toLowerCase()));
  const rawValue = Number(raw);
  const numericValid = Boolean(raw.trim()) && Number.isFinite(rawValue) && rawValue >= 0 && rawValue <= max && max > 0;

  async function perform(key: string, value: number, intent: "check" | "prepare" = "check") {
    if (!device || busy) return;
    const deviceId = device.device_id;
    setBusy(key); setActionError(""); setReview(null);
    try {
      const result = await checkSinvertCommand(deviceId, key, value);
      if (!mounted.current || selectedRef.current !== deviceId) return;
      setOutcome({ result, at: new Date().toISOString(), kind: "check" });
      if (result.success && intent === "prepare" && writable) setReview({key,value,deviceId});
    } catch (error) { setActionError(error instanceof Error ? error.message : "Verifica non riuscita"); }
    finally { setBusy(null); }
  }
  async function sendReviewed() {
    if (!device || !review || review.deviceId !== device.device_id || !writable || busy) return;
    const action = review; setReview(null); setBusy(action.key); setActionError("");
    try {
      const result = await sendDeviceCommand(device.device_id, action.key, { value: action.value });
      setOutcome({ result, at: new Date().toISOString(), kind: "send" });
      void fetchData(device.device_id);
    } catch (error) { setActionError(error instanceof Error ? error.message : "Esito non disponibile: verificare lo stato prima di ripetere."); }
    finally { setBusy(null); }
  }
  async function saveLimit() {
    if (!device || saving) return;
    setSaving(true); setSettingsMessage("");
    try {
      if (!limit.trim()) throw new Error("Inserire un limite numerico; 0 disabilita l’invio.");
      await saveSinvertReferenceLimit(device.device_id, Number(limit));
      setSettingsMessage("Limite locale salvato. Nessun riferimento inviato al PLC.");
      await fetchData(device.device_id);
    } catch (error) { setSettingsMessage(error instanceof Error ? error.message : "Salvataggio non riuscito"); }
    finally { setSaving(false); }
  }
  function openDiagnostics(index: number) { setGroupIndex(index); setTab("diagnostics"); }
  const group = monitor?.groups.find(entry => entry.index === groupIndex);
  useEffect(() => {
    if (!review) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = document.getElementById("sv-review-dialog");
    const controls = () => Array.from(dialog?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
    controls()[0]?.focus();
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function keyboard(event: KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); setReview(null); }
      if (event.key !== "Tab") return;
      const list = controls(); const first = list[0]; const last = list[list.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener("keydown", keyboard);
    return () => { document.removeEventListener("keydown", keyboard); document.body.style.overflow = oldOverflow; previous?.focus(); };
  }, [review]);
  useEffect(() => {
    if (outcome || actionError) outcomeRef.current?.scrollIntoView({ behavior: "auto", block: "nearest" });
  }, [outcome, actionError]);

  return <div className="sv-shell">
    <aside className="sv-sidebar">
      <a className="sv-brand" href="/sinvert.html"><span className="sv-brand-mark"><Icon name="bolt" size={24}/></span><span>PV Guardian<small>CONTROL WORKSPACE</small></span></a>
      <div className="sv-workspace-label">WORKSPACE LOCALE <span>LAB</span></div>
      <nav aria-label="Navigazione SINVERT">{tabs.map(item => <button key={item.key} className={tab === item.key ? "active" : ""} aria-current={tab === item.key ? "page" : undefined} onClick={() => setTab(item.key)}><Icon name={item.icon}/>{item.label}{item.key === "alarms" && alarms.length > 0 && <em>{alarms.length}</em>}</button>)}</nav>
      <div className="sv-sidebar-divider"/>
      <p className="sv-nav-caption">CONNESSIONE SELEZIONATA</p>
      <div className="sv-plc-tile"><Icon name="chip"/><div><strong>PLC SINVERT</strong><span>{String(device?.connection_settings.host ?? "Nessun PLC")}</span></div><i className={`sv-dot sv-dot--${fresh ? "ok" : "muted"}`}/></div>
      <div className="sv-sidebar-bottom"><div><Icon name="lock" size={16}/><span>Anteprima di valutazione</span></div><p>Apertura in sola consultazione. I comandi richiedono il collaudo manuale.</p><a href="/">Apri PV Guardian <Icon name="arrow" size={16}/></a></div>
    </aside>
    <div className="sv-workspace">
      <header className="sv-topbar"><div><span className="sv-breadcrumb">Dispositivi di campo</span><span>/</span><strong>SINVERT</strong><span className="sv-preview">Anteprima locale</span></div><div><span className="sv-live"><i className={`sv-dot sv-dot--${fresh ? "ok" : "muted"}`}/>{fresh ? "Dati dal PLC" : "Dati da verificare"}</span><span className="sv-avatar">PV</span></div></header>
      <main className="sv-main">
        <div className="sv-page-heading"><div><div className="sv-eyebrow">SUPERVISIONE E CONTROLLO</div><h1>{tabs.find(item => item.key === tab)?.label === "Panoramica" ? "Controllo SINVERT" : tabs.find(item => item.key === tab)?.label}</h1><p>Un solo punto di controllo. Stato dei gruppi, disponibilità e richieste al PLC.</p></div><div className="sv-page-actions"><span><Icon name="clock" size={15}/>{timestamp(overview?.diagnostics.last_valid_data_at)}</span><button className="sv-button sv-button--white" disabled={loading || !selected} onClick={() => void fetchData(selected)}><Icon name="refresh" size={16}/>Aggiorna</button></div></div>
        {devices.length > 1 && <label className="sv-selector">PLC da visualizzare<select value={selected} disabled={Boolean(busy)} onChange={event => setSelected(event.target.value)}>{devices.map(item => <option value={item.device_id} key={item.device_id}>{item.name}</option>)}</select></label>}
        {loadError && <div className="sv-notice sv-notice--bad" role="alert"><Icon name="alert"/><div><strong>Acquisizione non disponibile</strong><p>{loadError} Gli ultimi valori non sono un consenso operativo.</p></div></div>}
        {loading && !overview ? <Empty>Acquisizione dello stato del PLC…</Empty> : !device ? <Empty>Nessun dispositivo SINVERT configurato. Aggiungi il PLC in PV Guardian per visualizzarlo qui.</Empty> : !monitor ? <Empty>Diagnostica SINVERT non disponibile. Attendere il prossimo campione o verificare il profilo del dispositivo.</Empty> : <>
          <section className="sv-status-strip" aria-label="Stato collegamenti"><div><span className="sv-status-icon"><Icon name="chip"/></span><div><small>CONTROLLER</small><strong>SIMATIC S7-300</strong><span>{String(device.connection_settings.host)} · CP343-1</span></div><Badge tone={fresh ? "ok" : "warn"}>{connection}</Badge></div><span className="sv-status-separator"/><div><span className="sv-status-icon"><Icon name="link"/></span><div><small>FEEDBACK INVERTER</small><strong>{fresh ? `${reporting.length} di ${configured.length} gruppi con dati validi` : "Non confermati"}</strong><span>Distinti dalla connessione Ethernet al PLC</span></div></div><span className="sv-status-separator"/><div><span className="sv-status-icon"><Icon name="settings"/></span><div><small>MODALITÀ INTERFACCIA</small><strong>{manual ? "Collaudo manuale" : "Consultazione"}</strong><span>{manual ? "Controlli PLC sempre attivi" : "Nessuna scrittura abilitata in questa pagina"}</span></div></div></section>

          {tab === "overview" && <>
            <div className={`sv-readiness ${!fresh || startBlocked ? "sv-readiness--warn" : "sv-readiness--ok"}`}><Icon name={!fresh || startBlocked ? "alert" : "check"} size={23}/><div><h2>{!fresh ? "Stato operativo da aggiornare" : startBlocked ? "Avvio non disponibile" : "Consensi presenti nel campione"}</h2><p>{!fresh ? "Attendere dati aggiornati prima di valutare i comandi." : startBlocked ? problems[0] : "La verifica del programma e dei consensi viene ripetuta prima di ogni invio."}</p></div><button onClick={() => setTab("commissioning")}>Vedi condizioni <Icon name="arrow" size={17}/></button></div>
            <section className="sv-kpis" aria-label="Riepilogo unità"><Metric label="GRUPPI CONFIGURATI" value={`${configured.length}`} unit="/ 4" note="Posizioni abilitate dal programma" icon="grid"/><Metric label="POTENZA ATTIVA" value={number(power)} unit="kW" note={power === null ? "Misura non disponibile o qualità non confermata" : "Somma dei gruppi · scala da validare sul campo"} icon="bolt"/><Metric label="BIT DI ALLARME ATTIVI" value={fresh ? String(alarms.length) : "—"} note="Finestre monitorate dei gruppi configurati" icon="alert" tone={alarms.length ? "bad" : "muted"}/><Metric label="ULTIMA ACQUISIZIONE" value={number(overview?.diagnostics.response_time_ms,0)} unit="ms" note={`${overview?.telemetry.length ?? 0} punti · ${overview?.diagnostics.failed_points ?? 0} errori di lettura`} icon="clock"/></section>
            <div className="sv-overview-layout"><div><div className="sv-section-title"><div><h2>Inverter dell’unità</h2><p>Disponibilità e misure riportate dal PLC.</p></div><span>FINO A 4 GRUPPI</span></div><div className="sv-inverter-grid">{monitor.groups.map(item => <GroupCard key={item.index} group={item} fresh={fresh} select={() => openDiagnostics(item.index)}/>)}</div><div className="sv-data-footnote"><Icon name="chip" size={16}/><p>Le indicazioni ON e contattore AC condividono la stessa logica del controller: non sono due conferme fisiche indipendenti.</p></div></div>
              <aside className="sv-control-column"><section className="sv-panel"><div className="sv-panel-heading"><Icon name="settings"/><h2>Controllo del gruppo</h2></div><p>Le richieste agiscono su tutte le posizioni gestite da questo PLC.</p><button className="sv-button sv-button--primary sv-button--full" disabled={!writable || startBlocked || Boolean(busy)} onClick={() => void perform("sinvert_on_request",1,"prepare")}><Icon name="play" size={17}/>Avvia gruppo</button><button className="sv-button sv-button--stop sv-button--full" disabled={!writable || Boolean(busy)} onClick={() => void perform("sinvert_off_request",1,"prepare")}><Icon name="stop" size={16}/>Arresta gruppo</button><div className="sv-control-hint"><Icon name="lock" size={16}/><span>{!manual ? "Comandi disponibili nella modalità Collaudo." : !fresh ? "Servono dati aggiornati dal PLC." : startBlocked ? "Avvio bloccato dalle condizioni del PLC." : "Ogni richiesta passa da una verifica preventiva."}</span></div><button className="sv-text-button" onClick={() => setTab("commissioning")}>Apri collaudo manuale <Icon name="arrow" size={16}/></button></section>
                <section className="sv-panel sv-power-panel"><div className="sv-panel-heading"><Icon name="bolt"/><h2>Regolazione potenza</h2></div><Badge tone="warn">Scala da validare</Badge><div className="sv-power-placeholder">— <small>kW / %</small></div><p>La conversione del riferimento non è ancora confermata. Il collaudo tecnico utilizza valori PLC grezzi.</p><button className="sv-text-button" onClick={() => setTab("commissioning")}>Vedi riferimento tecnico <Icon name="arrow" size={16}/></button></section>
              </aside></div>
          </>}

          {tab === "alarms" && <section className="sv-panel sv-table-panel"><div className="sv-section-title"><div><h2>Messaggi attivi del PLC</h2><p>Gruppi configurati · {fresh ? "ultimo campione disponibile" : "campione non aggiornato"}</p></div><Badge tone={alarms.length ? "bad" : "muted"}>{alarms.length} bit di allarme</Badge></div><div className="sv-table-tools"><div className="sv-segmented">{[["all","Tutti"],["alarm","Allarmi"],["warning","Avvisi"]].map(([value,label]) => <button key={value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>{label}</button>)}</div><input aria-label="Cerca messaggi" placeholder="Cerca messaggio, inverter o indirizzo…" value={search} onChange={event => setSearch(event.target.value)}/></div><div className="sv-table-scroll"><table><thead><tr><th>Tipo</th><th>Inverter</th><th>Descrizione documentale</th><th>Indirizzo</th><th>Fonte</th></tr></thead><tbody>{filtered.map(message => <tr key={`${message.index}-${message.address}`}><td><Badge tone={message.kind === "alarm" ? "bad" : "warn"}>{message.kind === "alarm" ? "Allarme" : "Avviso"}</Badge></td><td>INV {String(message.index).padStart(2,"0")}</td><td>{message.label}</td><td><code>{message.address}</code></td><td>{message.manual_page ? `Manuale, p. ${message.manual_page}` : "Non documentato"}</td></tr>)}</tbody></table>{!filtered.length && <Empty>{messages.length ? "Nessun messaggio corrisponde al filtro." : "Nessun bit attivo nel campione delle finestre monitorate. Questo non certifica l’assenza di ogni allarme dell’impianto."}</Empty>}</div><p className="sv-source-note">Descrizioni dal manuale Siemens V1.0, da verificare nella variante software. Sono monitorati i primi 128 bit di avvisi e allarmi per inverter. Letture incomplete: {configured.some(item => !item.messages_complete) ? "sì" : "no"}.</p></section>}

          {tab === "commissioning" && <>
            <div className="sv-notice"><Icon name="settings"/><div><strong>Collaudo manuale · intero PLC</strong><p>Verifica le condizioni, prepara la richiesta e controlla l’esito. Una risposta S7 positiva non conferma il movimento o la produzione dell’inverter.</p></div></div>
            <div className="sv-commissioning-grid"><section className="sv-panel"><div className="sv-panel-heading"><h2>1. Condizioni di controllo</h2><Badge tone={fresh && !startBlocked ? "ok" : "warn"}>{fresh && !startBlocked ? "Da verificare online" : "Blocchi presenti"}</Badge></div><ul className="sv-condition-list"><Condition ok={fresh} title="Collegamento al PLC" detail={fresh ? "Dati aggiornati disponibili" : "Collegamento o dati non confermati"}/><Condition ok={reporting.length === configured.length && configured.length > 0 && fresh} title="Feedback dei gruppi" detail={`${fresh ? reporting.length : 0} di ${configured.length} gruppi con misure di qualità confermata dal PLC`}/><Condition ok={fresh && !startBlocked} title="Disponibilità all’avvio" detail={problems[0] ?? "Nessun blocco nel campione; serve la verifica online"}/><Condition ok={monitor.manual_enabled && commissioning} title="Profilo di collaudo" detail={monitor.manual_enabled && commissioning ? "Abilitato nelle impostazioni locali" : "Scritture non abilitate nel profilo"}/></ul><button className="sv-button sv-button--white" disabled={Boolean(busy)} onClick={() => void perform("sinvert_on_request",1)}><Icon name="refresh" size={16}/>{busy === "sinvert_on_request" ? "Verifica in corso…" : "Verifica avvio · sola lettura"}</button><details className="sv-details"><summary>Tutte le condizioni rilevate</summary><ul>{[...new Set(monitor.power_blockers.map(explainBlocker))].map(item => <li key={item}>{item}</li>)}</ul></details></section>
              <section className="sv-panel"><div className="sv-panel-heading"><h2>2. Richieste manuali</h2><Icon name="lock"/></div><label className="sv-toggle"><input type="checkbox" checked={manual} disabled={!commissioning || !monitor.manual_enabled} onChange={event => { setManual(event.target.checked); setReview(null); }}/><span><strong>Abilita i comandi in questa pagina</strong><small>Non modifica i consensi del PLC. Si disattiva riaprendo la pagina.</small></span></label><div className="sv-command-pair"><button className="sv-button sv-button--primary" disabled={!writable || startBlocked || Boolean(busy)} onClick={() => void perform("sinvert_on_request",1,"prepare")}><Icon name="play" size={16}/>Prepara avvio</button><button className="sv-button sv-button--stop" disabled={!writable || Boolean(busy)} onClick={() => void perform("sinvert_off_request",1,"prepare")}><Icon name="stop" size={16}/>Prepara arresto</button></div><button className="sv-text-button" disabled={Boolean(busy)} onClick={() => void perform("sinvert_off_request",1)}>Verifica arresto senza inviare <Icon name="arrow" size={16}/></button><p className="sv-source-note">L’arresto software non sostituisce l’arresto di emergenza dell’impianto.</p></section></div>
            <section className="sv-panel"><div className="sv-section-title"><div><h2>Riferimento di potenza · collaudo tecnico</h2><p>Valori PLC grezzi. Nessuna equivalenza automatica con kW o percentuale.</p></div><Badge tone="warn">Unità da confermare</Badge></div><div className="sv-reference-track">{[["Esterno",monitor.reference_chain.controller_a_external_raw],["Copia PLC",monitor.reference_chain.controller_a_copied_raw],["Ingresso regolatore",monitor.reference_chain.controller_a_input_raw],["Dopo selezione / rampa",monitor.reference_chain.controller_a_processed_raw]].map(([label,value], index) => <div key={String(label)}><span><em>{index+1}</em>{label}</span><strong>{fresh ? number(value as number | null,3) : "—"}</strong></div>)}</div><p className="sv-source-note">Fallback configurato: {number(monitor.reference_chain.controller_fallback_a,3)}. La ricezione di un valore non dimostra che sia stato selezionato o applicato dall’inverter.</p><div className="sv-reference-form"><label>Riferimento da verificare <span>VALORE PLC · MAX {number(max,3)}</span><input type="number" min="0" max={max} step="any" placeholder="Inserisci un valore PLC" value={raw} onChange={event => setRaw(event.target.value)}/></label><button className="sv-button sv-button--white" disabled={!numericValid || Boolean(busy)} onClick={() => void perform("sinvert_power_reference_raw",rawValue)}>Verifica senza inviare</button><button className="sv-button sv-button--primary" disabled={!numericValid || !writable || monitor.power_blockers.length > 0 || Boolean(busy)} onClick={() => void perform("sinvert_power_reference_raw",rawValue,"prepare")}>Prepara riferimento <Icon name="arrow" size={16}/></button></div><details className="sv-details"><summary>Impostazioni del limite locale · attuale {number(max,3)}</summary><p>Questo limite controlla l’intervallo accettato dall’app, non la potenza nominale. Con 0 l’invio è disabilitato.</p><div className="sv-reference-form"><label>Massimo valore PLC consentito<input type="number" min="0" max="1000000" step="any" value={limit} placeholder={String(max)} onChange={event => setLimit(event.target.value)}/></label><button className="sv-button sv-button--white" disabled={saving || !limit.trim()} onClick={() => void saveLimit()}>{saving ? "Salvataggio…" : "Salva solo nell’app"}</button></div>{settingsMessage && <p role="status">{settingsMessage}</p>}</details></section>
          </>}

          {tab === "diagnostics" && <div className="sv-diagnostic-layout"><section className="sv-panel"><div className="sv-section-title"><div><h2>Origine dei segnali</h2><p>Dati di progetto per la verifica tecnica.</p></div><select aria-label="Inverter da analizzare" value={groupIndex} onChange={event => setGroupIndex(Number(event.target.value))}>{monitor.groups.map(item => <option key={item.index} value={item.index}>Inverter {item.index}</option>)}</select></div>{group && <><dl className="sv-definition-list"><div><dt>Configurato nel PLC</dt><dd>{group.configured === null ? "Non noto" : group.configured ? "Sì" : "No"}</dd></div><div><dt>Codice stato della variante</dt><dd>{group.state_code ?? "—"} · {group.state_label}</dd></div><div><dt>Segnale disponibilità M55</dt><dd>{group.consent === null ? "Non noto" : group.consent ? "Attivo" : "Assente"}</dd></div><div><dt>ON HMI / contattore AC HMI</dt><dd>{group.hmi_on == null ? "—" : String(group.hmi_on)} / {group.hmi_ac_contactor == null ? "—" : String(group.hmi_ac_contactor)}</dd></div><div><dt>Qualità delle misure</dt><dd>{group.measurement_quality}</dd></div></dl><h3>Condizioni della formula</h3>{group.consent_reasons.length ? <ul className="sv-technical-reasons">{group.consent_reasons.map(item => <li key={item}><code>{item}</code></li>)}</ul> : <p>Nessuna discrepanza rilevata tra le sorgenti acquisite.</p>}<div className="sv-notice"><Icon name="chip"/><p>I feedback HMI ON e contattore AC derivano dalla stessa formula M55. Il campione non è atomico rispetto alla scansione PLC.</p></div></>}</section><section className="sv-panel"><h2>Acquisizione</h2><dl className="sv-definition-list"><div><dt>Protocollo</dt><dd>S7 TCP · porta {String(device.connection_settings.port ?? 102)}</dd></div><div><dt>Rack / slot</dt><dd>{String(device.connection_settings.rack ?? 0)} / {String(device.connection_settings.slot ?? 2)}</dd></div><div><dt>Ultimo campione</dt><dd>{timestamp(overview?.diagnostics.last_valid_data_at)}</dd></div><div><dt>Punti esposti</dt><dd>{overview?.telemetry.length ?? 0}</dd></div><div><dt>Letture non riuscite</dt><dd>{overview?.diagnostics.failed_points ?? 0}</dd></div><div><dt>Conferma fisica dei comandi</dt><dd>Non validata</dd></div></dl><details className="sv-details"><summary>Telemetria grezza e qualità</summary><div className="sv-table-scroll sv-raw-table"><table><thead><tr><th>Segnale</th><th>Raw</th><th>Valore</th></tr></thead><tbody>{overview?.telemetry.map(point => <tr key={point.key}><td>{point.label}</td><td><code>{String(point.raw_value ?? "—")}</code></td><td>{point.display_value} {point.unit}</td></tr>)}</tbody></table></div></details></section></div>}

          {(outcome || actionError) && <section ref={outcomeRef} className="sv-panel sv-outcome" aria-live="polite"><div className="sv-panel-heading"><h2>Ultima operazione</h2><span>{outcome ? timestamp(outcome.at) : ""}</span></div>{actionError ? <div className="sv-notice sv-notice--bad"><Icon name="alert"/><p>{actionError}</p></div> : outcome && <><div className="sv-outcome-title"><Badge tone={outcome.result.success ? "ok" : "warn"}>{outcome.kind === "check" ? "Verifica in sola lettura" : "Richiesta al PLC"}</Badge><strong>{commandNames[outcome.result.command] ?? outcome.result.command}</strong></div><p>{outcome.kind === "check" ? outcome.result.success ? "Controlli superati. Nessun comando è stato inviato." : outcome.result.message : outcome.result.message}</p><div className="sv-result-steps"><span className={outcome.result.diagnostics.write_accepted ? "done" : ""}><Icon name={outcome.result.diagnostics.write_accepted ? "check" : "clock"} size={16}/>Accettazione S7</span><Icon name="arrow" size={15}/><span className={outcome.result.diagnostics.request_consumed || outcome.result.diagnostics.regulator_input_confirmed ? "done" : ""}><Icon name={outcome.result.diagnostics.request_consumed || outcome.result.diagnostics.regulator_input_confirmed ? "check" : "clock"} size={16}/>Elaborazione PLC</span><Icon name="arrow" size={15}/><span><Icon name="clock" size={16}/>Riscontro fisico non confermato</span></div><details className="sv-details"><summary>Dettagli tecnici dell’esito</summary><pre>{JSON.stringify(outcome.result.diagnostics,null,2)}</pre></details></>}</section>}
        </>}
        <footer className="sv-footer"><span><i className="sv-dot sv-dot--ok"/>PV Guardian Lab · SINVERT</span><span>Anteprima locale · integrazione definitiva da valutare</span><span>{timestamp(overview?.diagnostics.last_valid_data_at)} · nessun dato simulato</span></footer>
      </main>
    </div>
    <nav className="sv-mobile-nav" aria-label="Navigazione mobile SINVERT">{tabs.map(item => <button key={item.key} className={tab === item.key ? "active" : ""} aria-current={tab === item.key ? "page" : undefined} onClick={() => setTab(item.key)}><Icon name={item.icon} size={20}/>{item.label}</button>)}</nav>
    {busy && <div className="sv-working" role="status"><Icon name="refresh" size={17}/>{commandNames[busy] ?? "Operazione"} ? controlli in corso?</div>}
    {review && <div className="sv-modal-backdrop" onClick={() => setReview(null)}><section id="sv-review-dialog" className="sv-modal" role="dialog" aria-modal="true" aria-labelledby="sv-review-title" onClick={event => event.stopPropagation()}><button className="sv-modal-close" onClick={() => setReview(null)} aria-label="Chiudi riepilogo"><Icon name="close"/></button><div className="sv-modal-icon"><Icon name={review.key === "sinvert_off_request" ? "stop" : "settings"} size={25}/></div><div className="sv-eyebrow">RIEPILOGO DELLA RICHIESTA</div><h2 id="sv-review-title">{commandNames[review.key]}</h2><p>Destinazione: <strong>{String(device?.connection_settings.host)}</strong>. Ambito: <strong>tutte le posizioni gestite dal PLC</strong>.</p>{review.key === "sinvert_power_reference_raw" && <p>Riferimento: <strong>{number(review.value,3)} · valore PLC grezzo</strong>.</p>}<p>La verifica preventiva è stata superata. All’invio il driver ripeterà i controlli. L’accettazione del PLC non conferma l’esecuzione fisica.</p><div className="sv-command-pair"><button className="sv-button sv-button--white" onClick={() => setReview(null)}>Annulla</button><button className="sv-button sv-button--primary" disabled={!writable} onClick={() => void sendReviewed()}>Invia richiesta al PLC <Icon name="arrow" size={16}/></button></div></section></div>}
  </div>;
}

function Metric({ label, value, unit, note, icon, tone }: { label: string; value: string; unit?: string; note: string; icon: string; tone?: Tone }) {
  return <article className={`sv-metric ${tone === "bad" ? "sv-metric--alert" : ""}`}><div><span>{label}</span><Icon name={icon} size={18}/></div><strong>{value} {unit && <small>{unit}</small>}</strong><p>{note}</p></article>;
}
function Condition({ ok, title, detail }: { ok: boolean; title: string; detail: string }) {
  return <li><span className={`sv-condition-icon ${ok ? "sv-condition-icon--ok" : ""}`}><Icon name={ok ? "check" : "alert"} size={17}/></span><div><strong>{title}</strong><p>{detail}</p></div></li>;
}
