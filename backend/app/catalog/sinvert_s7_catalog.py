"""SINVERT M/TL diagnostics, with separately attributed HMI and raw signals."""
from dataclasses import replace
from app.models.inverter_model import InverterModel, InverterPoint

COMMISSIONING_MODEL = "M/TL S7-300 - Collaudo comandi"
HMI_COMMANDS = {f"sinvert_unit_{i}_{action}": (i, 842+194*(i-1), 0 if action=="operator_pulse" else 1)
                for i in range(1,5) for action in ("test_mode","operator_pulse","reset")}
COMMISSIONING_COMMANDS = set(HMI_COMMANDS) | {"sinvert_on_request", "sinvert_off_request", "sinvert_power_reference_raw", "sinvert_alarm_ack"}


def _point(key: str, label: str, db: int, offset: int, datatype: str = "uint16", *, bit: int | None = None, area: str = "DB") -> InverterPoint:
    length = 1 if datatype in {"bool", "uint8"} else (4 if datatype in {"float32", "uint32", "int32"} else 2)
    meta = {"driver": "sinvert_s7", "area": area, "db": db, "section": "Diagnostica PLC", "semantics": "raw_plc_value"}
    if bit is not None:
        meta["bit"] = bit
    return InverterPoint(key=key, label=label, kind="telemetry", register_type="s7", address=offset,
                         length=length, datatype=datatype, protocol_meta=meta)


def build_sinvert_s7_models() -> list[InverterModel]:
    points = [
        _point("external_copy_enabled_a", "Consenso copia esterna A", 100, 135, "bool", bit=0),
        _point("external_copy_enabled_b", "Consenso copia esterna B", 100, 135, "bool", bit=1),
        _point("external_reference_raw", "Riferimento esterno grezzo", 511, 10, "float32"),
        _point("copied_reference_raw", "Riferimento copiato grezzo", 402, 10, "float32"),
        _point("event_a_raw", "Evento interno A", 0, 34, "bool", bit=0, area="MK"),
        _point("event_b_raw", "Evento interno B", 0, 34, "bool", bit=1, area="MK"),
        _point("mask_feedback_a", "Feedback logico maschera A", 126, 34, "bool", bit=0),
        _point("mask_feedback_b", "Feedback logico maschera B", 126, 34, "bool", bit=1),
        _point("mtl_mode_raw", "Modalita M/TL PLC", 100, 3, "bool", bit=4),
        _point("controller_a_external_raw", "Riferimento regolatore A: esterno grezzo", 511, 32, "float32"),
        _point("controller_b_external_raw", "Riferimento regolatore B: esterno grezzo", 511, 36, "float32"),
        _point("controller_a_copied_raw", "Riferimento regolatore A: copiato grezzo", 944, 32, "float32"),
        _point("controller_b_copied_raw", "Riferimento regolatore B: copiato grezzo", 944, 36, "float32"),
    ]
    for unit in range(4):
        points.extend([
            _point(f"unit_{unit+1}_reference_raw", f"Unita {unit+1}: riferimento grezzo", 126, 10+150*unit),
            _point(f"unit_{unit+1}_bank_raw", f"Unita {unit+1}: selettore banco", 120, 60+74*unit),
            _point(f"unit_{unit+1}_buffer_raw", f"Unita {unit+1}: buffer numerico grezzo", 120, 42+74*unit),
            _point(f"unit_{unit+1}_flag_raw", f"Unita {unit+1}: indicatore logico grezzo", 0, 55, "bool", bit=unit, area="MK"),
        ])
    # Siemens HMI V1.0 pp.30-49, crossed with extracted HMI producer
    # group199..204. Never reuse the manual's obsolete state enumeration.
    points.extend([
        _point("configured_groups_raw", "Gruppi configurati (MB51)", 0, 51, "uint8", area="MK"),
        _point("hmi_unit_status_raw", "Stato aggregato variante PLC", 402, 18, "uint8"),
        _point("hmi_unit_flags_raw", "Stati generali HMI", 402, 14, "uint8"),
        _point("external_consent_raw", "Consenso esterno (DB3.0.7)", 3, 0, "bool", bit=7),
        _point("external_watchdog_fault", "Watchdog esterno scaduto", 600, 24, "bool", bit=4),
        _point("external_channel_fault", "Errore canale esterno", 600, 24, "bool", bit=1),
        _point("plc_requests_raw", "Richieste interne M34", 0, 34, "uint8", area="MK"),
        _point("plc_output_requests_raw", "Maschera richieste M102..105", 0, 102, "uint32", area="MK"),
        _point("plc_sequence_raw", "Sequenza DB64.26", 64, 26, "uint8"),
        _point("plc_reset_raw", "Reset M0.4", 0, 0, "bool", bit=4, area="MK"),
        _point("plc_reinitialize_raw", "Reinizializzazione M23.1", 0, 23, "bool", bit=1, area="MK"),
        _point("controller_a_input_raw", "Ingresso A regolatore FB570", 570, 2, "float32"),
        _point("controller_b_input_raw", "Ingresso B regolatore FB570", 570, 6, "float32"),
        _point("controller_a_processed_raw", "Riferimento A dopo selezione/rampa",570,140,"float32"),
        _point("controller_a_scaled_raw", "Riferimento A interno moltiplicato per 1000",570,28,"float32"),
        _point("controller_available_groups", "Gruppi contati dal regolatore",570,192),
        _point("controller_output_raw", "Uscita logica FB570.DBX18.0 (soglia bassa)",570,18,"bool",bit=0),
        _point("controller_fallback_a", "Fallback A configurato",579,70,"float32"),
        _point("controller_fallback_b", "Fallback B configurato",579,74,"float32"),
    ])
    for unit in range(4):
        number=unit+1; hmi=842+194*unit
        points.extend([
            _point(f"unit_{number}_comm_flag_a",f"INV{number}: segnale comunicazione A",120,6+74*unit,"bool",bit=1),
            _point(f"unit_{number}_comm_flag_b",f"INV{number}: segnale comunicazione B",120,7+74*unit,"bool",bit=6),
        ])
        for key,label,db,offset,datatype in [
            ("hmi_status_raw", "Stato variante PLC",402,hmi+22,"uint8"),
            ("hmi_flags_raw", "Feedback HMI (derivati da M55)",402,hmi+2,"uint8"),
            ("consent_status_raw", "Sorgenti consenso DB120",120,59+74*unit,"uint8"),
            ("active_power", "Potenza attiva",402,hmi+106,"int16"),
            ("reactive_power", "Potenza reattiva",402,hmi+110,"int16"),
            ("frequency", "Frequenza",402,hmi+112,"int16"),
            ("voltage_l1", "Tensione AC L1",402,hmi+100,"int16"),
            ("dc_voltage", "Tensione DC",402,hmi+72,"int16"),
            ("dc_current", "Corrente DC",402,hmi+46,"int16"),
            ("dc_contactor_raw", "Contattori DC: segnali di ingresso",402,hmi+4,"uint8"),
            ("alarm_word_0", "Allarmi: primi 32 bit",401,144+128*unit,"uint32"),
            ("warning_word_0", "Avvisi: primi 32 bit",401,128+128*unit,"uint32"),
        ]:
            point=_point(f"unit_{number}_{key}", f"INV{number}: {label}",db,offset,datatype)
            scale,unit_label={"active_power":(.1,"kW"),"reactive_power":(.1,"kvar"),
                "frequency":(.01,"Hz"),"voltage_l1":(1.,"V"),"dc_voltage":(.1,"V"),
                "dc_current":(.1,"A")}.get(key,(1.,""))
            points.append(replace(point,scale=scale,unit=unit_label,protocol_meta={**point.protocol_meta,
                "section":f"INV{number} - Monitoraggio HMI","semantics":"documented_hmi",
                "source":"Siemens S7 HMI V1.0 + extracted group199..204", "physical_validation":False}))
        for word in range(1,4):
            for kind,offset,label in [("alarm",144,"Allarmi"),("warning",128,"Avvisi")]:
                point=_point(f"unit_{number}_{kind}_word_{word}",f"INV{number}: {label} bit {word*32}..{word*32+31}",401,offset+128*unit+4*word,"uint32")
                points.append(replace(point,protocol_meta={**point.protocol_meta,"section":f"INV{number} - Monitoraggio HMI"}))
    for unit in range(1,5):
        base=842+194*(unit-1)
        points.extend([
            _point(f"unit_{unit}_test_mode", f"INV{unit}: selettore AUTO/TEST",402,base,"bool",bit=1),
            _point(f"unit_{unit}_operator_request", f"INV{unit}: pulsante operatore",402,base,"bool",bit=0),
            _point(f"unit_{unit}_test_feedback", f"INV{unit}: eco selettore AUTO/TEST",402,base+2,"bool",bit=1),
        ])
    diagnostic = InverterModel(
        brand="SINVERT", model="M/TL S7-300 - Diagnostica", protocol="s7_tcp", transport="tcp",
        defaults={"port": 102, "rack": 0, "slot": 2, "timeout_seconds": 5, "retries": 0, "poll_interval_seconds": 15},
        features=["diagnostica PLC S7", "sola lettura", "semantica fisica da validare"], telemetry_points=points,
        command_points=[],
    )
    commands=[]
    for key,label,address,datatype,maximum in [
        ("sinvert_on_request","ON: richiesta collettiva al PLC",34,"uint16",1),
        ("sinvert_off_request","OFF: richiesta collettiva al PLC",34,"uint16",1),
        ("sinvert_power_reference_raw","Potenza: riferimento A (valore PLC, collaudo)",32,"float32",1000000),
    ]:
        commands.append(InverterPoint(key=key,label=label,kind="command",register_type="s7",address=address,
            length=4 if datatype=="float32" else 1,datatype=datatype,writable=True,
            protocol_meta={"driver":"sinvert_s7_commissioning","section":"Collaudo SINVERT",
                "min_value":0 if datatype=="float32" else 1,"max_value":maximum,
                "step":0.1 if datatype=="float32" else 1,"manual_only":True}))
    commands.append(InverterPoint(key="sinvert_alarm_ack",label="Reset allarmi: riconoscimento collettivo",kind="command",register_type="s7",address=0,length=1,datatype="uint16",writable=True,
        protocol_meta={"driver":"sinvert_s7_commissioning","section":"Collaudo SINVERT","min_value":1,"max_value":1,"step":1,"manual_only":True}))
    for key,(unit,offset,bit) in HMI_COMMANDS.items():
        commands.append(InverterPoint(key=key,label=f"INV{unit}: " + ("Reset (impulso AUTO/TEST)" if key.endswith("_reset") else "AUTO/TEST (0=AUTO, 1=TEST)" if bit else "Pulsante operatore a impulso"),
            kind="command",register_type="s7",address=offset,length=1,datatype="uint16",writable=True,
            protocol_meta={"driver":"sinvert_s7_commissioning","section":"Collaudo SINVERT",
                "min_value":0 if bit and not key.endswith("_reset") else 1,"max_value":1,"step":1,"manual_only":True}))
    return [diagnostic,InverterModel(brand="SINVERT",model=COMMISSIONING_MODEL,protocol="s7_tcp",transport="tcp",
        defaults={**diagnostic.defaults,"sinvert_write_mode":"read_only","sinvert_reference_max_raw":0},
        features=["collaudo manuale","programma PLC verificato","scala fisica da confermare"],
        telemetry_points=points,command_points=commands)]
