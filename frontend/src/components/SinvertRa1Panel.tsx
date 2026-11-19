import type { DeviceOverview } from "../api";
import { sinvertDeviceUrl } from "../sinvert/routing";

const format = (value: number | null | undefined) =>
  value == null ? "—" : new Intl.NumberFormat("it-IT", { maximumFractionDigits: 3 }).format(value);

export function SinvertRa1Panel({ overview }: { overview: DeviceOverview }) {
  const monitor = overview.diagnostics.sinvert_ra1;
  if (!monitor) return null;
  const fresh = overview.diagnostics.data_freshness === "fresh";
  return (
    <><section className="detail-section">
      <h3>SINVERT RA1 · 420 S7-300</h3>
      <p>
        {fresh && monitor.program_verified ? "Programma PLC riconosciuto" : "Verificare freschezza e identificazione PLC"}
        {" · "}Telemetria RA1 · {format(monitor.position_count)} posizioni
      </p>
      <div className="detail-kpi-grid">
        <article><h4>Canale CP</h4><p>{monitor.cp_enabled == null ? "Dato assente" : monitor.cp_enabled ? "Abilitato" : "Disabilitato nel PLC"}</p></article>
        <article><h4>Parametri del canale</h4><p>{monitor.cp_parameters_match ? "Conformi al progetto RA1" : "Da verificare"}</p></article>
      </div>
      <h4>Riferimenti del regolatore</h4>
      <p>Valori PLC grezzi. Scala fisica da confermare; nessuna equivalenza automatica con kW o percentuale.</p>
      <table>
        <thead><tr><th>Riferimento</th><th>Ricevuto dal CP</th><th>Ingresso regolatore</th><th>Dopo selezione / rampa</th></tr></thead>
        <tbody>
          <tr><td>A</td><td>{format(monitor.reference_a)}</td><td>{format(monitor.regulator_a)}</td><td>{format(monitor.processed_a)}</td></tr>
          <tr><td>B</td><td>{format(monitor.reference_b)}</td><td>{format(monitor.regulator_b)}</td><td>Vedi telemetria gruppi</td></tr>
        </tbody>
      </table>
      <h4>Condizioni da verificare prima del controllo</h4>
      <ul>{monitor.blockers.map(reason => <li key={reason}>{reason}</li>)}</ul>
    </section><a className="secondary-button" href={sinvertDeviceUrl(overview.device.device_id)+"&tab=commissioning"}>Apri la dashboard dedicata e il collaudo SINVERT RA1</a></>
  );
}
