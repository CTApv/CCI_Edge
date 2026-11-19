import { useEffect, useState } from "react";
import { getRa1Lab, runRa1Lab, type Ra1LabResult } from "../api";

export function SinvertRa1LabPanel({ deviceId, enabled = false, referenceLimit = 0 }: { deviceId: string; enabled?: boolean; referenceLimit?: number }) {
  const [mode, setMode] = useState("bench");
  const [value, setValue] = useState("");
  const [maximum, setMaximum] = useState("");
  const [localTsap, setLocalTsap] = useState("");
  const [remoteTsap, setRemoteTsap] = useState("");
  const [cpuOnly, setCpuOnly] = useState(false);
  const [connectionConfirmed, setConnectionConfirmed] = useState(false);
  const [exclusive, setExclusive] = useState(false);
  const [session, setSession] = useState<Ra1LabResult | null>(null);
  const [result, setResult] = useState<Ra1LabResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reachable, setReachable] = useState(false);
  useEffect(() => { setMaximum(String(referenceLimit)); }, [referenceLimit]);

  useEffect(() => {
    let cancelled = false;
    let running = false;
    const refresh = async () => {
      if (running) return;
      running = true;
      try {
        const next = await getRa1Lab(deviceId);
        if (!cancelled) {
          setSession(next); setReachable(true);
          if (["starting", "active", "stopping"].includes(next.state ?? "")) {
            setMode("native");
            if (next.maximum != null) setMaximum(String(next.maximum));
            setValue(previous => previous || String(next.raw_value ?? ""));
          }
        }
      } catch {
        if (!cancelled) setReachable(false);
      } finally { running = false; }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [deviceId]);

  const occupied = !!session && ["starting", "active", "stopping", "bench_probe", "command"].includes(session.state ?? "");
  const valid = value.trim() !== "" && maximum.trim() !== "" && Number.isFinite(Number(value)) &&
    Number.isFinite(Number(maximum)) && Number(maximum) > 0 && Number(maximum) <= 1000000 && Number(maximum) <= referenceLimit &&
    Number(value) >= 0 && Number(value) <= Number(maximum) && Number(value) <= referenceLimit;
  const act = async (action: string, payload?: Record<string, unknown>) => {
    setBusy(true); setError(""); setResult(null);
    try {
      const next = await runRa1Lab(deviceId, action, payload);
      setResult(next);
      setSession(await getRa1Lab(deviceId));
    } catch (e) { setError(e instanceof Error ? e.message : "Operazione non riuscita. Verificare lo stato prima di ripetere."); }
    finally { setBusy(false); }
  };
  const current = result?.feedback ?? session?.feedback;
  return <section className="detail-section">
    <h3>Collaudo SINVERT RA1</h3>
    {!enabled && <p>Profilo in sola lettura. Abilitare il collaudo nelle impostazioni della dashboard SINVERT RA1.</p>}
    <p>Riferimento A in unità PLC grezze. Il collaudo non certifica potenza fisica, percentuale o risposta dell’inverter.</p>
    <label>Percorso di prova <select value={mode} disabled={busy || occupied} onChange={e => { setMode(e.target.value); setResult(null); }}>
      <option value="bench">Prova S7 temporanea · solo CPU e CP isolati</option>
      <option value="native">Sessione CP continua · inverter collegato</option>
    </select></label>
    <div className="detail-kpi-grid">
      <label>Riferimento A grezzo <input type="number" min="0" step="any" value={value} disabled={busy} onChange={e => setValue(e.target.value)} /></label>
      <label>Limite massimo della prova <input type="number" min="0" max={referenceLimit} step="any" value={maximum} disabled={busy || occupied} onChange={e => setMaximum(e.target.value)} /></label>
    </div>
    {mode === "bench" ? <>
      <p>Scrive temporaneamente DB944.DBD32, controlla l’ingresso del regolatore e ripristina il valore iniziale. Richiede ramo CP, consensi e uscite inattivi. Questa prova non alimenta né verifica il watchdog CP.</p>
      <label><input type="checkbox" checked={cpuOnly} disabled={busy} onChange={e => setCpuOnly(e.target.checked)} /> Confermo sola CPU e CP, senza inverter o periferiche collegati.</label>
    </> : <>
      <p>Invia un telegramma ogni 0,8 s e verifica ricezione, ingresso del regolatore e watchdog. La sessione dura 60 s e richiede rinnovo manuale. Consensi e abilitazioni PLC devono essere già presenti.</p>
      <div className="detail-kpi-grid">
        <label>TSAP locale IOT (esadecimale) <input value={localTsap} disabled={busy || occupied} onChange={e => { setLocalTsap(e.target.value); setConnectionConfirmed(false); }} /></label>
        <label>TSAP remoto CP (esadecimale) <input value={remoteTsap} disabled={busy || occupied} onChange={e => { setRemoteTsap(e.target.value); setConnectionConfirmed(false); }} /></label>
      </div>
      <label><input type="checkbox" checked={connectionConfirmed} disabled={busy || occupied} onChange={e => setConnectionConfirmed(e.target.checked)} /> Ho verificato partner, TSAP e apertura attiva dall’IOT nella configurazione CP.</label>
      <label><input type="checkbox" checked={exclusive} disabled={busy || occupied} onChange={e => setExclusive(e.target.checked)} /> Confermo controllo esclusivo del canale e idoneità del valore grezzo e del limite per questa prova.</label>
      <p>Interrompere gli invii chiude il canale. Non è un comando OFF: il comportamento successivo dipende dal fallback PLC, da verificare sul campo.</p>
    </>}
    <div className="detail-actions">
      <button type="button" className="secondary-button" disabled={busy || !reachable || occupied} onClick={() => void act("preflight", { bench: mode === "bench" })}>Verifica senza scrivere</button>
      {mode === "bench" ? <button type="button" disabled={busy || !enabled || !reachable || occupied || !valid || !cpuOnly} onClick={() => void act("probe", { value: Number(value), maximum: Number(maximum), cpu_only_confirmed: cpuOnly })}>Esegui prova S7 e ripristina</button> : <>
        <button type="button" disabled={busy || !enabled || !reachable || occupied || !valid || !localTsap.trim() || !remoteTsap.trim() || !connectionConfirmed || !exclusive} onClick={() => void act("start", { value: Number(value), maximum: Number(maximum), local_tsap: localTsap.trim(), remote_tsap: remoteTsap.trim(), connection_confirmed: connectionConfirmed, exclusive_confirmed: exclusive })}>Avvia sessione CP</button>
        <button type="button" disabled={busy || !enabled || !reachable || !session?.active || !valid} onClick={() => void act("reference", { value: Number(value), renew: false })}>Invia nuovo riferimento</button>
        <button type="button" disabled={busy || !enabled || !reachable || !session?.active || session.raw_value == null} onClick={() => void act("reference", { value: session?.raw_value, renew: true })}>Rinnova per 60 s</button>
      </>}
      <button type="button" className="secondary-button" disabled={busy || !occupied || session?.state === "bench_probe"} onClick={() => void act("stop")}>Interrompi invii CP</button>
    </div>
    <p role="status">{reachable ? `Sessione: ${{ stopped: "ferma", starting: "avvio", active: "attiva", stopping: "arresto", fault: "errore", bench_probe: "prova S7" }[session?.state ?? "stopped"] ?? session?.state}. ${session?.active ? `Scade fra ${session.remaining_seconds} s; telegrammi inviati: ${session.sent_count}.` : ""}` : "Stato del collaudo non disponibile: verificare il collegamento prima di ripetere operazioni."}</p>
    {busy && <p>Operazione in corso…</p>}
    {current && <p>Ultimo riscontro: ricevuto {current.received_raw ?? "—"}, ingresso regolatore {current.regulator_raw ?? "—"}, dopo rampa {current.processed_raw ?? "—"}. Watchdog: {current.watchdog_fault ? "scaduto" : "non scaduto"}; errore ricezione: {current.receive_error ? "sì" : "no"}.</p>}
    {result?.success != null && <p role="status">{result.success ? "Verifica superata" : "Verifica non superata"}{result.restored != null ? ` · ripristino ${result.restored ? "confermato" : "non confermato"}` : ""}. {result.feedback?.regulator_input_confirmed ? "Ingresso del regolatore confermato durante la prova." : ""}</p>}
    {(error || result?.error || session?.error) && <p role="alert">{error || result?.error || session?.error}</p>}
  </section>;
}
