"""GT500 families are not aliases of the legacy Xanbus GT Series map."""
from app.models.inverter_model import InverterModel, InverterPoint

GT500_GATEWAY_DRIVER = "xantrex_gt500_pvgt"
GT500_E_MODELS = ("GT500 E / PVGT12542EDI", "GT500 E GI / PVGT12542EDI")
GT500_NATIVE_MODELS = ("GT500 MVX", "GT500 MVX PG", "GT500 480", "GT500 480 PG", "GT500 600", "GT500 600 PG")
GT500_E_SOURCE = "https://manualzilla.com/doc/6114549/manuale-uso-gt500e--gt630e"
GT500_MVX_SOURCE = "https://iproduct.ils.org.tw/ProductClass/download.aspx?f=Manual%2FProduct%2F71%2FGT500_Operation_EN.pdf"
GT500_480_SOURCE = "https://manuals.plus/m/70d4e9da29e4257c43c19b8c40b4dc794c3466dfb278e4aadc56e9e7477f8f13.pdf"


def is_gt500_family(brand: str, model: str) -> bool:
    return brand == "Xantrex" and model in (*GT500_E_MODELS, *GT500_NATIVE_MODELS)


GT500_FIELD_FIRMWARE = (0x0710, 0x0C0D)
GT500_SYSTEM_STATES = {0: "Inizializzazione", 1: "Disabilitato", 2: "Attesa DC", 3: "Avvio",
    4: "Produzione MPPT", 5: "Corrente manuale", 6: "Test matrice", 7: "Guasto"}


def build_gt500_gateway_points() -> list[InverterPoint]:
    # PVGT table 1-1 uses one-based register numbers. PDU offsets and
    # 0.1 kW power scaling commissioned on firmware 0710/0C0D, 2026-11-27.
    fields = [
        ("gateway_communication_status", "Collegamento gateway", 0, "uint16", 1, "", {}),
        ("goal_state", "Stato obiettivo", 1, "uint16", 1, "", {}),
        ("system_state", "Stato sistema", 2, "uint16", 1, "", {"summary_metric": "status", "enum_map": GT500_SYSTEM_STATES}),
        ("fault_code", "Codice guasto (valore decimale)", 3, "uint16", 1, "", {"enum_map": {0: "Nessun guasto", 53: "0035 - Classe guasto 35"}}),
        ("inverter_state", "Stato inverter", 4, "uint16", 1, "", {}),
        ("pv_state", "Stato impianto FV", 5, "uint16", 1, "", {}),
        ("software_version_high", "Versione software H grezza", 6, "uint16", 1, "", {}),
        ("software_version_low", "Versione software L grezza", 7, "uint16", 1, "", {}),
        ("ac_voltage_ab_v", "Tensione A-B", 12, "uint16", 1, "V", {}),
        ("ac_voltage_bc_v", "Tensione B-C", 13, "uint16", 1, "V", {}),
        ("ac_voltage_ca_v", "Tensione C-A", 14, "uint16", 1, "V", {}),
        ("active_power_kw", "Potenza attiva", 18, "int16", 0.1, "kW", {"summary_metric": "power_kw"}),
        ("temperature_c", "Temperatura matrice", 19, "int16", 1, "C", {"summary_metric": "temperature_c"}),
        ("dc_voltage_v", "Tensione DC", 21, "uint16", 1, "V", {}),
        ("dc_current_a", "Corrente DC", 22, "int16", 1, "A", {}),
        ("dc_power_kw", "Potenza DC", 23, "int16", 0.1, "kW", {}),
        ("grid_frequency_hz", "Frequenza rete", 24, "uint16", 0.1, "Hz", {}),
        ("active_power_limit", "Limite corrente MPPT", 31, "uint16", 1, "%", {"command": "active_power_limit", "valid_min": 0, "valid_max": 100}),
    ]
    return [InverterPoint(key=key, label=label, kind="telemetry", register_type="holding",
        address=address, length=1, datatype=datatype, scale=scale, unit=unit, protocol_meta={
            "driver": GT500_GATEWAY_DRIVER, "manual_register": address + 1,
            "section": "GT500 E / PVGT12542EDI", "heartbeat": address == 0, **meta,
        }) for key, label, address, datatype, scale, unit, meta in fields]


def build_gt500_gateway_commands() -> list[InverterPoint]:
    return [InverterPoint(key="active_power_limit", label="Limite corrente/potenza MPPT", kind="command",
        register_type="holding", address=31, length=1, datatype="uint16", unit="%", writable=True,
        protocol_meta={"driver": GT500_GATEWAY_DRIVER, "manual_register": 32, "min_value": 0,
            "max_value": 100, "step": 1, "section": "Controllo potenza", "force_multi_write": True})]


def build_xantrex_gt500_models(protocol: str, transport: str) -> list[InverterModel]:
    if (protocol, transport) not in {("modbus_tcp", "tcp"), ("modbus_rtu", "serial")}:
        return []
    profiles = []
    if protocol == "modbus_tcp":
        for name in GT500_E_MODELS:
            profiles.append(InverterModel(brand="Xantrex", model=name, protocol=protocol, transport=transport,
                defaults={"host": "192.168.1.254", "port": 502, "unit_id": 1,
                    "timeout_seconds": 2.0, "retries": 0, "poll_interval_seconds": 15,
                    "test_register": 0, "test_function": "holding", "test_count": 34, "xantrex_pvgt_control_enabled": False},
                features=["Telemetria PVGT e stato guasti", "Limite MPPT 0-100%, passo 1%",
                    "Conferma ritardata del riferimento", "Comandi solo dopo collaudo del gateway"],
                telemetry_points=build_gt500_gateway_points(), command_points=build_gt500_gateway_commands(),
                catalog_meta={"series": "GT500 E / gateway PVGT", "verification_status": "field_tested" if name == GT500_E_MODELS[0] else "documented_not_field_tested",
                    "field_tested": name == GT500_E_MODELS[0], "source_document": "Schneider/Xantrex 975-0582-01-01",
                    "source_version": "Giugno 2010 Rev B, tabella 1-1", "source_url": GT500_E_SOURCE,
                    "last_reviewed_at": "2026-11-27", "operational": True, "discovery_enabled": False, "scope": "pvgt_mppt_control",
                    "notes": "GT500 E collaudato su gateway Schneider XAGT10042ED, firmware inverter 0710/0C0D. Abilitare xantrex_pvgt_control_enabled solo dopo verifica della mappa sul sito. Limite corrente MPPT persistente, non APC ID 85/86; nessuna scadenza automatica. Una sola sessione TCP condivisa da polling e comandi. Guasti sospendono i comandi. Variante GI da collaudare separatamente."}))

    for name in GT500_NATIVE_MODELS:
        mvx = "MVX" in name
        defaults = {"timeout_seconds": 2.0, "retries": 0, "poll_interval_seconds": 15}
        defaults.update({"host": "", "port": 502, "unit_id": 200} if protocol == "modbus_tcp" else
            {"port": "", "slave_id": 200, "baud_rate": 9600, "parity": "N", "byte_size": 8, "stop_bits": 1})
        profiles.append(InverterModel(brand="Xantrex", model=name, protocol=protocol, transport=transport,
            defaults=defaults, features=["Non operativo: mappa registri da acquisire",
                "RS485/Modbus con kit previsto dal costruttore", "TCP richiede gateway compatibile"],
            catalog_meta={"series": "GT500 MVX" if mvx else "GT500 480/600",
                "verification_status": "documentation_pending", "field_tested": False,
                "source_document": "Schneider/Xantrex 975-0554-01-01" if mvx else "Schneider/Xantrex 975-0602-01-01",
                "source_url": GT500_MVX_SOURCE if mvx else GT500_480_SOURCE,
                "last_reviewed_at": "2026-11-17", "operational": False,
                "notes": "Sottofamiglia identificata, driver non operativo. I manuali disponibili non definiscono una mappa Modbus verificata. Test e creazione dispositivo bloccati; nessuna lettura o scrittura automatica. Non usa la mappa GT Series/Xanbus. Parametri seriali e Unit ID vanno verificati sul kit installato."}))
    return profiles
