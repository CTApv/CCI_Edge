import type { DeviceOverview } from "../api";

export function ra1View(overview: DeviceOverview | null, failed = false) {
  const points = new Map(overview?.telemetry.map(p => [p.key, p]) ?? []);
  const value = (key: string): number | null => {
    const p = points.get(key);
    return p && p.quality !== "invalid" && p.quality !== "unavailable" && typeof p.raw_value === "number" && Number.isFinite(p.raw_value) ? p.raw_value : null;
  };
  const flag = (key: string): boolean | null => {
    const p = points.get(key);
    return p && p.quality !== "invalid" && p.quality !== "unavailable" && typeof p.raw_value === "boolean" ? p.raw_value : null;
  };
  const configured = value("ra1_configured_groups");
  const ready = value("ra1_ready_groups");
  const fresh = !failed && overview?.diagnostics.data_freshness === "fresh" && overview?.diagnostics.communication_state === "online";
  const groups = [1,2,3,4].map(index => {
    const prefix = `ra1_group_${index}_`;
    const messages: { kind: "alarm" | "warning"; address: string; bit: number }[] = [];
    let complete = true;
    for (const kind of ["alarm", "warning"] as const) for (let word = 0; word < 4; word++) {
      const raw = value(prefix + kind + "_" + word);
      if (raw == null) { complete = false; continue; }
      const base = (kind === "alarm" ? 144 : 128) + 128 * (index - 1) + word * 4;
      for (let bit = 0; bit < 32; bit++) if ((raw >>> bit) & 1) {
        messages.push({ kind, address: `DB401.DBX${base + 3 - Math.floor(bit / 8)}.${bit % 8}`, bit: word * 32 + bit });
      }
    }
    return { index, configured: configured == null ? null : !!(configured & (1 << (index - 1))),
      consent: ready == null ? null : !!(ready & (1 << (index - 1))), state: value(prefix + "state"),
      active: value(prefix + "active_power_raw"), reactive: value(prefix + "reactive_power_raw"),
      dcVoltage: value(prefix + "dc_voltage_raw"), dcCurrent: value(prefix + "dc_current_raw"),
      frequency: value(prefix + "frequency_raw"), test: flag(prefix + "test_mode"),
      messages, complete };
  });
  return { fresh, groups, monitor: overview?.diagnostics.sinvert_ra1, value, flag,
    messages: groups.filter(g => g.configured === true).flatMap(g => g.messages.map(m => ({ ...m, group: g.index }))) };
}
