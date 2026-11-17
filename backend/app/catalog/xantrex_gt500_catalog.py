"""GT500 families are not aliases of the legacy Xanbus GT Series map."""
from app.models.inverter_model import InverterModel, InverterPoint

GT500_GATEWAY_DRIVER = "xantrex_gt500_pvgt_diagnostics"
GT500_E_MODELS = ("GT500 E / PVGT12542EDI", "GT500 E GI / PVGT12542EDI")
GT500_NATIVE_MODELS = ("GT500 MVX", "GT500 MVX PG", "GT500 480", "GT500 480 PG", "GT500 600", "GT500 600 PG")
GT500_E_SOURCE = "https://manualzilla.com/doc/6114549/manuale-uso-gt500e--gt630e"
GT500_MVX_SOURCE = "https://iproduct.ils.org.tw/ProductClass/download.aspx?f=Manual%2FProduct%2F71%2FGT500_Operation_EN.pdf"
GT500_480_SOURCE = "https://manuals.plus/m/70d4e9da29e4257c43c19b8c40b4dc794c3466dfb278e4aadc56e9e7477f8f13.pdf"


def is_gt500_family(brand: str, model: str) -> bool:
    return brand == "Xantrex" and model in (*GT500_E_MODELS, *GT500_NATIVE_MODELS)


def build_gt500_gateway_points() -> list[InverterPoint]:
    # Table 1-1, manual 975-0582-01-01, pp. 1-20/1-26. Only the
    # unambiguous first eight single-word diagnostic fields are exposed.
    fields = [
        ("gateway_communication_status", "Collegamento gateway: 0 valido, 4 errore"),
        ("goal_state", "Stato obiettivo"), ("system_state", "Stato sistema"),
        ("fault_code", "Codice guasto grezzo"), ("inverter_state", "Stato inverter"),
        ("pv_state", "Stato impianto FV"), ("software_version_high", "Versione software H grezza"),
        ("software_version_low", "Versione software L grezza"),
    ]
    return [InverterPoint(key=key, label=label, kind="telemetry", register_type="holding",
        address=index, length=1, datatype="uint16", protocol_meta={
            "driver": GT500_GATEWAY_DRIVER, "manual_register": index + 1,
            "section": "Diagnostica GT500 / PVGT12542EDI", "heartbeat": index == 0,
            "engineering_value": False,
        }) for index, (key, label) in enumerate(fields)]


def build_xantrex_gt500_models(protocol: str, transport: str) -> list[InverterModel]:
    if (protocol, transport) not in {("modbus_tcp", "tcp"), ("modbus_rtu", "serial")}:
        return []
    profiles = []
    if protocol == "modbus_tcp":
        for name in GT500_E_MODELS:
            profiles.append(InverterModel(brand="Xantrex", model=name, protocol=protocol, transport=transport,
                defaults={"host": "192.168.1.254", "port": 502, "unit_id": 1,
                    "timeout_seconds": 2.0, "retries": 0, "poll_interval_seconds": 15,
                    "test_register": 0, "test_function": "holding", "test_count": 8},
                features=["Solo diagnostica: stati e guasto", "Convertitore PVGT12542EDI richiesto",
                    "Misure e modulazione non ancora abilitate", "Nessuna scrittura durante il polling"],
                telemetry_points=build_gt500_gateway_points(),
                catalog_meta={"series": "GT500 E / gateway PVGT", "verification_status": "diagnostic_only",
                    "field_tested": False, "source_document": "Schneider/Xantrex 975-0582-01-01",
                    "source_version": "Giugno 2010 Rev B, tabella 1-1", "source_url": GT500_E_SOURCE,
                    "last_reviewed_at": "2026-11-17", "operational": True, "discovery_enabled": False, "scope": "diagnostics_only",
                    "notes": "Solo stati grezzi, senza conferma identita o potenza. Convenzione registro 1 = PDU 0 da collaudare sul gateway. Unit ID da verificare; 1 e un valore iniziale software. APC ID 85/86 non sono indirizzi Modbus verificati. Nessuna compatibilita implicita con altri gateway."}))
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
