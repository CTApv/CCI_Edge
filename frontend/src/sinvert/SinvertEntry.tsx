import { useEffect, useState } from "react";
import { getDevices } from "../api";
import { SinvertDashboard } from "./SinvertDashboard";
import { SinvertRa1Dashboard } from "./SinvertRa1Dashboard";
import { requestedSinvertDevice } from "./routing";

export function SinvertEntry() {
  const [selected, setSelected] = useState<{ ra1: boolean; id: string } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    getDevices().then(list => {
      if (cancelled) return;
      const requested = requestedSinvertDevice(window.location.search);
      const device = requested ? list.find(d => d.device_id === requested) : list.find(d => d.protocol === "s7_tcp" && ["SINVERT", "SINVERT RA1"].includes(d.brand));
      if (device?.brand === "SINVERT RA1" && device.protocol === "s7_tcp") setSelected({ ra1: true, id: device.device_id });
      else setSelected({ ra1: false, id: requested ?? "" });
    }).catch(e => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, []);
  if (error) return <div className="sv-empty" role="alert">{error}<a href="/">Torna a PV Guardian</a></div>;
  if (!selected) return <div className="sv-empty">Selezione del profilo SINVERT…</div>;
  return selected.ra1 ? <SinvertRa1Dashboard deviceId={selected.id}/> : <SinvertDashboard/>;
}
