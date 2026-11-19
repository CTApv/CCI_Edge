"""Separate RA1 family, based on the uploaded test sinvert 420 application."""
from app.models.inverter_model import InverterModel, InverterPoint

RA1_BRAND = "SINVERT RA1"
RA1_MODEL = "420 S7-300 - KOMM 3.0 / REGEL 3.9"
RA1_DRIVER = "sinvert_ra1_s7"
RA1_BLOCKS = {
    "OB1": (1426, 34806), "FC30": (6420, 51855), "FC55": (594, 22860),
    "FC120": (4308, 31914), "FC501": (2760, 4368), "FB64": (1292, 29356),
    "FB570": (3026, 23313), "FB572": (532, 60708), "FC10": (4706, 59415),
    "FC60": (4162, 26829), "FC402": (9756, 18032), "FB18": (162, 4938),
}
RA1_DB_SIZES = {64:164, 100:158, 120:298, 126:600, 511:64, 600:64,
                944:64, 401:640, 402:1618, 570:246, 579:98}


def is_ra1_device(device):
    return getattr(device, "brand", "") == RA1_BRAND and getattr(device, "model", "") == RA1_MODEL


def ra1_points():
    points = []
    def add(key, label, db, offset, datatype="uint16", *, bit=None, area="DB", section="SINVERT RA1"):
        size = 1 if datatype in ("bool", "uint8") else 4 if datatype in ("float32", "uint32") else 2
        meta = {"driver": RA1_DRIVER, "area": area, "db": db,
                "section": section, "semantics": "ra1_raw_plc_value"}
        if bit is not None:
            meta["bit"] = bit
        points.append(InverterPoint(key=key, label=label, kind="telemetry", register_type="s7",
                                    address=offset, length=size, datatype=datatype, protocol_meta=meta))
    add("ra1_cp_enabled", "Canale esterno abilitato", 400, 16, "bool", bit=7)
    add("ra1_external_consent", "Consenso esterno PLC", 3, 0, "bool", bit=7)
    add("ra1_copy_a", "Abilitazione copia HMI A", 100, 135, "bool", bit=0)
    add("ra1_external_b", "Abilitazione esterna B / copia HMI B", 100, 135, "bool", bit=1)
    add("ra1_position_count", "Posizioni configurate", 100, 6)
    add("ra1_configured_groups", "Maschera gruppi configurati", 0, 51, "uint8", area="MK")
    add("ra1_ready_groups", "Maschera consensi gruppi", 0, 55, "uint8", area="MK")
    add("ra1_receive_event", "Nuovo telegramma CP", 600, 24, "bool", bit=0)
    add("ra1_receive_error", "Errore ricezione CP", 600, 24, "bool", bit=1)
    add("ra1_watchdog_fault", "Comunicazione esterna scaduta", 600, 24, "bool", bit=4)
    add("ra1_requests", "Richieste collettive M34", 0, 34, "uint8", area="MK")
    add("ra1_sequence", "Sequenza collettiva DB64", 64, 26, "uint8")
    add("ra1_reset_active", "Reset PLC attivo", 0, 0, "bool", bit=4, area="MK")
    add("ra1_reinitialize", "Reinizializzazione PLC attiva", 0, 23, "bool", bit=1, area="MK")
    for key, label, offset in [
        ("tx_id", "ID invio", 0), ("tx_laddr", "LADDR invio", 2),
        ("tx_db", "DB invio", 4), ("tx_offset", "Offset invio", 6), ("tx_length", "Byte invio", 8),
        ("rx_id", "ID ricezione", 16), ("rx_laddr", "LADDR ricezione", 18),
        ("rx_db", "DB ricezione", 20), ("rx_offset", "Offset ricezione", 22),
        ("rx_length", "Byte ricezione", 28),
    ]:
        add("ra1_"+key, label, 600, offset, section="Canale CP RA1")
    for key, label, db, offset in [
        ("hmi_reference_a", "Buffer HMI A", 511, 32), ("hmi_reference_b", "Buffer HMI B", 511, 36),
        ("received_reference_a", "Riferimento A ricevuto nel DB944", 944, 32),
        ("received_reference_b", "Riferimento B ricevuto nel DB944", 944, 36),
        ("regulator_input_a", "Ingresso A del regolatore", 570, 2),
        ("regulator_input_b", "Ingresso B del regolatore", 570, 6),
        ("processed_reference_a", "Riferimento A dopo selezione e rampa", 570, 140),
        ("distributed_reference_b", "Riferimento B distribuito ai gruppi", 570, 148),
        ("fallback_a", "Default A configurato", 579, 70), ("fallback_b", "Default B configurato", 579, 74),
    ]:
        add("ra1_"+key, label+" (valore PLC)", db, offset, "float32", section="Riferimenti RA1")
    for index in range(4):
        group=index+1;hmi=842+194*index
        for key,label,db,offset,datatype in [
            ("consent_status", "Sorgenti consenso", 120, 59+74*index, "uint8"),
            ("state", "Stato HMI grezzo", 402, hmi+22, "uint8"),
            ("active_power_raw", "Potenza attiva PLC grezza", 402, hmi+106, "int16"),
            ("reactive_power_raw", "Potenza reattiva PLC grezza", 402, hmi+110, "int16"),
            ("dc_voltage_raw", "Tensione DC PLC grezza", 402, hmi+72, "int16"),
            ("dc_current_raw", "Corrente DC PLC grezza", 402, hmi+46, "int16"),
            ("frequency_raw", "Frequenza PLC grezza", 402, hmi+112, "int16"),
            ("voltage_ac_raw", "Tensione AC PLC grezza", 402, hmi+100, "int16"),
        ]:
            add(f"ra1_group_{group}_{key}", label, db, offset, datatype, section=f"RA1 - Gruppo {group}")
        add(f"ra1_group_{group}_test_mode", "Selettore AUTO/TEST", 402, hmi, "bool", bit=1, section=f"RA1 - Gruppo {group}")
        add(f"ra1_group_{group}_operator_request", "Pulsante operatore", 402, hmi, "bool", bit=0, section=f"RA1 - Gruppo {group}")
        for word in range(4):
            for kind, offset in (("alarm", 144), ("warning", 128)):
                add(f"ra1_group_{group}_{kind}_{word}", f"{kind}: bit {word*32}..{word*32+31}",
                    401, offset+128*index+word*4, "uint32", section=f"RA1 - Gruppo {group}")
    return points


def build_sinvert_ra1_models():
    return [InverterModel(brand=RA1_BRAND, model=RA1_MODEL, protocol="s7_tcp", transport="tcp",
        defaults={"port":102, "rack":0, "slot":2, "timeout_seconds":10,
                  "retries":0, "poll_interval_seconds":15, "ra1_write_mode":"read_only", "ra1_reference_max_raw":0},
        features=["Driver SINVERT RA1 separato", "Firma del programma PLC verificata",
                  "Canale CP diretto DB944", "ON/OFF e reset manuali RA1", "AUTO/TEST e pulsanti per gruppo", "Dashboard SINVERT dedicata", "Tracce RA1 ZIP/CSV", "Collaudo tecnico RA1 separato"],
        telemetry_points=ra1_points(), command_points=ra1_commands(),
        catalog_meta={"series":"SINVERT RA1 / test sinvert 420", "verification_status":"diagnostic_only",
            "source_document":"test sinvert 420 - TIA V18; PLC MC7 comparison 2026-11-19",
            "source_version":"KOMM 3.0 / REGEL 3.9", "last_reviewed_at":"2026-11-19",
            "field_tested":False, "writes_enabled":False, "commissioning_available":True, "reference_scale_confirmed":False,
            "source_sha256":"cdb781c67e11a4d9bf6b636c6bef19f40c41fb29b297ba517ea634d1fee0c25d",
            "notes":"18 blocchi di controllo confrontati byte per byte; 12 verificati nelle letture e 18 nei comandi. Quattro gruppi; 420 identifica il progetto, non una potenza nominale certificata. Scala fisica, partner CP e TSAP da confermare. Collaudo tecnico separato: prova S7 isolata e sessione CP con TSAP confermati. Nessun comando di flotta."})]


def ra1_commands():
    """Discoverable manual capabilities. Generic I/O is deliberately not authorized."""
    specs=[('on','ON collettivo',34,1,'uint8'),('off','OFF collettivo',34,1,'uint8'),
           ('reset_all','Reset dei gruppi configurati',842,1,'uint8'),
           ('reference_a','Riferimento A grezzo (collaudo)',32,4,'float32')]
    for group in range(1,5):
        for action,label in [('test','AUTO/TEST'),('operator','Pulsante operatore'),('reset','Reset gruppo')]:
            specs.append((f'group_{group}_{action}',f'Gruppo {group}: {label}',842+194*(group-1),1,'uint8'))
    return [InverterPoint(key='sinvert_ra1_'+key,label=label,kind='command',register_type='s7',
            address=offset,length=length,datatype=datatype,writable=True,
            protocol_meta={'driver':'sinvert_ra1_manual','manual_only':True,'command_alias':key,
                'section':'Collaudo SINVERT RA1','requires_dedicated_api':True,
                'min_value':0 if key.endswith('_test') or key=='reference_a' else 1,
                'max_value':1000000 if key=='reference_a' else 1,'step':.1 if key=='reference_a' else 1})
            for key,label,offset,length,datatype in specs]
