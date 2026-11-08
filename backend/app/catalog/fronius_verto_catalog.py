"""Verto ROW profiles from the Fronius 1.2.7-2 SunSpec workbooks.

Offsets include the two model header words, and are resolved at runtime.
The format is detected from DID 103/113, never from a fixed absolute map.
"""
import json
from pathlib import Path

from app.models.inverter_model import InverterModel, InverterPoint

FRONIUS_DRIVER = "fronius_verto_sunspec"
MAP_SOURCE = json.loads(Path(__file__).with_name("fronius_sunspec_maps.json").read_text())


def sources(variant: str, did: int, name: str) -> list[dict[str, object]]:
    result = []
    for fmt in ("float", "int_sf"):
        actual_did = 103 if did == 113 and fmt == "int_sf" else did
        definition = MAP_SOURCE["maps"][f"{variant}_{fmt}"]["models"].get(str(actual_did))
        field = definition["fields"].get(name) if definition else None
        if not field or not field["supported"]:
            continue
        sf = definition["fields"].get(field["sf"]) if field["sf"] else None
        candidate = {"model_did": actual_did, "offset": field["offset"],
                     "length": field["length"], "datatype": field["type"],
                     "scale_factor_offset": sf["offset"] if sf else None}
        if candidate not in result:
            result.append(candidate)
    return result


def build_points(variant: str, mppts: int) -> list[InverterPoint]:
    points = []

    def add(key, label, did, name, *, unit="", scale=1.0, section="Inverter", summary=None):
        candidates = sources(variant, did, name)
        if not candidates:
            return
        first = candidates[0]
        meta = {"driver": FRONIUS_DRIVER, "sources": candidates, "section": section,
                "variant": variant, "sunspec_field": name}
        if summary:
            meta["summary_metric"] = summary
        if key == "power_limit_pct":
            meta["command"] = "active_power_limit"
            meta["readback_enabled_key"] = "power_limit_enabled"
        points.append(InverterPoint(key=key, label=label, kind="telemetry",
            register_type="holding", address=0, length=first["length"],
            datatype=first["datatype"], scale=scale, unit=unit, protocol_meta=meta))

    for key, name, label in [("manufacturer", "Mn", "Costruttore"),
                             ("device_model", "Md", "Modello rilevato"),
                             ("firmware_version", "Vr", "Firmware"),
                             ("serial_number", "SN", "Numero di serie")]:
        add(key, label, 1, name, section="Identità")
    add("active_power_kw", "Potenza attiva", 113, "W", unit="kW", scale=.001, summary="power_kw")
    add("total_energy_kwh", "Energia totale", 122, "ActWh", unit="kWh", scale=.001, summary="total_energy_kwh")
    add("ac_frequency_hz", "Frequenza rete", 113, "Hz", unit="Hz")
    add("ac_current_a", "Corrente AC totale", 113, "A", unit="A")
    add("apparent_power_kva", "Potenza apparente", 113, "VA", unit="kVA", scale=.001)
    add("reactive_power_kvar", "Potenza reattiva", 113, "VAr", unit="kvar", scale=.001)
    add("power_factor", "Fattore di potenza", 113, "PF", scale=.01)
    add("dc_power_kw", "Potenza DC totale", 113, "DCW", unit="kW", scale=.001)
    add("temperature_c", "Temperatura interna", 113, "TmpCab", unit="C", summary="temperature_c")
    add("operating_state", "Stato operativo SunSpec", 113, "St", summary="status")
    add("vendor_state", "Stato Fronius", 113, "StVnd")
    for phase in "ABC":
        add(f"ac_current_{phase.lower()}_a", f"Corrente fase {phase}", 113, f"Aph{phase}", unit="A")
        add(f"ac_voltage_{phase.lower()}_v", f"Tensione fase {phase}", 113, f"PhVph{phase}", unit="V")
    for pair in ("AB", "BC", "CA"):
        add(f"ac_voltage_{pair.lower()}_v", f"Tensione {pair}", 113, f"PPVph{pair}", unit="V")
    for name in ("Evt1", "Evt2", "EvtVnd1", "EvtVnd2"):
        add(name.lower(), f"Eventi {name}", 113, name, section="Diagnostica")
    for name in ("PVConn", "ECPConn"):
        add(name.lower(), f"Connessione {name}", 122, name, section="Stato")
    add("rated_power_kw", "Potenza nominale", 120, "WRtg", unit="kW", scale=.001, section="Targa")
    add("maximum_power_kw", "Base potenza WMax", 121, "WMax", unit="kW", scale=.001, section="Targa")
    for key, name, label, unit in [
        ("connection_request", "Conn", "Richiesta connessione", ""),
        ("power_limit_pct", "WMaxLimPct", "Limite potenza impostato", "%"),
        ("power_limit_enabled", "WMaxLim_Ena", "Limitazione potenza abilitata", ""),
        ("power_limit_revert_s", "WMaxLimPct_RvrtTms", "Timeout limite potenza", "s"),
        ("power_limit_ramp_s", "WMaxLimPct_RmpTms", "Rampa limite potenza", "s")]:
        add(key, label, 123, name, unit=unit, section="Controllo potenza")
    count = mppts + (2 if variant == "plus" else 0)
    for index in range(1, count+1):
        label = f"MPPT {index}" if index <= mppts else f"Batteria {'carica' if index == mppts+1 else 'scarica'}"
        for name, suffix, unit, scale in [("DCA", "current_a", "A", 1),
                    ("DCV", "voltage_v", "V", 1), ("DCW", "power_kw", "kW", .001),
                    ("DCWH", "energy_kwh", "kWh", .001)]:
            add(f"dc_channel_{index}_{suffix}", f"{label} · {name}", 160,
                f"module/{index}/{name}", unit=unit, scale=scale, section=label)
    if variant == "plus":
        for key, name, label, unit in [
            ("battery_soc_pct", "ChaState", "Stato di carica batteria", "%"),
            ("battery_state", "ChaSt", "Stato batteria", ""),
            ("battery_reserve_pct", "MinRsvPct", "Riserva batteria", "%"),
            ("storage_control_mode", "StorCtl_Mod", "Modalità accumulo", ""),
            ("battery_charge_limit_pct", "InWRte", "Limite carica batteria", "%"),
            ("battery_discharge_limit_pct", "OutWRte", "Limite scarica batteria", "%")]:
            add(key, label, 124, name, unit=unit, section="Accumulo")
    return points


def build_fronius_verto_models(protocol: str, transport: str) -> list[InverterModel]:
    models = []
    # Existing model names are retained; protocol selects the transport separately.
    series = [("Verto", ["15.0", "17.5", "20.0", "25.0", "27.0", "30.0", "33.3"]),
              ("Verto Plus", ["15.0", "17.5", "20.0", "25.0", "27.0", "30.0", "33.3"])]
    for family, powers in series:
        for power in powers:
            plus = family == "Verto Plus"
            variant = "plus" if plus else "3mppt" if float(power) < 25 else "4mppt"
            mppts = 4 if variant == "4mppt" else 3
            name = f"Verto {power}" + (" Plus" if plus else "")
            defaults = {"timeout_seconds": 2, "retries": 0, "poll_interval_seconds": 15,
                        "test_register": 40000, "test_count": 2, "test_function": "holding"}
            defaults.update({"host": "192.168.1.130", "port": 502, "unit_id": 1} if protocol == "modbus_tcp"
                else {"port": "COM1", "slave_id": 1, "baud_rate": 19200, "parity": "N", "stop_bits": 1, "byte_size": 8})
            commands = []
            for key, label, low, high, unit, action in [
                ("active_power_limit", "Limite potenza attiva (% di WMax)", 0, 100, "%", "power_limit"),
                ("start_inverter", "ON · connessione inverter", 1, 1, "", "connection"),
                ("stop_inverter", "OFF · disconnessione inverter", 0, 0, "", "connection"),
                ("disable_power_limit", "Disabilita limitazione potenza", 0, 0, "", "disable_limit")]:
                commands.append(InverterPoint(key=key, label=label, kind="command", register_type="holding",
                    address=0, length=1, datatype="uint16", unit=unit, writable=True,
                    protocol_meta={"driver": FRONIUS_DRIVER, "variant": variant, "action": action,
                        "expected_power_kw": float(power),
                        "min_value": low, "max_value": high, "step": .1 if unit else 1,
                        "section": "Controllo inverter", "default_value": low}))
            models.append(InverterModel(brand="Fronius", model=name, protocol=protocol, transport=transport,
                defaults=defaults, features=[family, f"{mppts} MPPT", "SunSpec float / int + SF automatico",
                    "ON/OFF Modbus", "Limite potenza 0–100% di WMax", "Accumulo in lettura" if plus else "Inverter fotovoltaico"],
                telemetry_points=build_points(variant, mppts), command_points=commands,
                catalog_meta={"series": family, "mppt_count": mppts, "rated_power_kw": float(power),
                    "verification_status": "documented_not_field_tested", "source_document": MAP_SOURCE["source"],
                    "source_version": MAP_SOURCE["version"], "last_reviewed_at": "2026-11-08", "field_tested": False,
                    "notes": "Mappe ufficiali ROW; abilitare controllo Modbus sull'inverter. Validato con simulatore, non su inverter fisico."}))
    return models
