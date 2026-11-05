"""Explain a read-only S7 sample. A sample never proves command execution.

State mapping comes from extracted HMI network17, not the older PDF enum.
M55 is an internally derived feedback and is not a second physical sensor.
"""
import math
import json
from pathlib import Path
from functools import lru_cache

STATE_LABELS={0:"Non determinato / non aggiornato",1:"Non in marcia",2:"In marcia (logica PLC)",
              3:"Avvisi presenti",4:"Allarmi presenti"}


@lru_cache(maxsize=1)
def _messages():
    return json.loads((Path(__file__).parent.parent/'catalog/sinvert_hmi_messages.json').read_text(encoding='utf8'))['messages']


def build_sinvert_monitor(values, settings=None):
    settings=settings or {}
    def integer(key):
        value=values.get(key)
        return value if type(value) is int else None
    def bit(value, index):
        return None if value is None else bool(value & (1<<index))
    configured=integer('configured_groups_raw')
    groups=[]
    for index in range(4):
        prefix=f'unit_{index+1}_'; status=integer(prefix+'consent_status_raw')
        flag=values.get(prefix+'flag_raw'); flag=flag if type(flag) is bool else None
        enabled=bit(configured,index); b4=bit(status,4); b5=bit(status,5); b6=bit(status,6)
        known=all(v is not None for v in [enabled,b4,b5,b6])
        expected=(enabled and not b4 and b5 and not b6) if known else None
        reasons=[]
        if enabled is False:reasons.append(f'M51.{index}=0: gruppo non configurato')
        offset=59+74*index
        for n,actual,required in [(4,b4,False),(5,b5,True),(6,b6,False)]:
            if actual is not None and actual!=required:
                reasons.append(f'DB120.DBX{offset}.{n}={int(actual)}: richiesto {int(required)}')
        if not known or flag is None:reasons.append('Sorgenti consenso non tutte leggibili')
        if expected is not None and flag is not None and expected!=flag:
            reasons.append('M55 non coincide con la formula: possibile cambio tra letture o variante software')
        code=integer(prefix+'hmi_status_raw'); hmi=integer(prefix+'hmi_flags_raw')
        comm_a=values.get(prefix+'comm_flag_a');comm_b=values.get(prefix+'comm_flag_b')
        # These flags feed the FC120 communication timeout, not an independent
        # assertion that the entire field installation is healthy.
        quality=("not_configured" if enabled is False else "missing" if enabled is None or code is None or comm_a is None or comm_b is None
                 else "communication_flags" if comm_a or comm_b else "unknown_state" if code not in {1,2,3,4} else "plc_reported")
        measures={}
        for key,scale in [('active_power',.1),('reactive_power',.1),('frequency',.01),('voltage_l1',1),('dc_voltage',.1),('dc_current',.1)]:
            raw=integer(prefix+key)
            measures[key]=raw*scale if raw is not None and quality=='plc_reported' else None
        messages=[];messages_complete=True
        for kind,base in [('alarm',144),('warning',128)]:
            for word in range(4):
                value=integer(prefix+f'{kind}_word_{word}')
                if value is None:messages_complete=False;continue
                for byte in range(4):
                    for n in range(8):
                        if not value&(1<<((3-byte)*8+n)):continue
                        address=f'{base+128*index+4*word+byte}.{n}'
                        definition=_messages().get(address,{})
                        messages.append({'address':'DB401.DBX'+address,'kind':kind,
                            'label':definition.get('label','Bit non descritto nel manuale'),
                            'manual_page':definition.get('page'),'label_verified_in_variant':False})
        groups.append({'index':index+1,'configured':enabled,'consent':flag,'expected_consent':expected,
            'consent_reasons':reasons,'state_code':code,'state_label':STATE_LABELS.get(code,f'Sconosciuto ({code})' if code is not None else 'Dato assente'),
            'hmi_on':bit(hmi,3),'hmi_ac_contactor':bit(hmi,2),'feedback_independent':False,
            'comm_flag_a':comm_a,'comm_flag_b':comm_b,'measurement_quality':quality,'measurements':measures,
            'messages_complete':messages_complete,'active_messages':messages})
    start=[]; power=[]
    def require(condition,message,target):
        if not condition:target.append(message)
    require(values.get('mtl_mode_raw') is True,'Modalità M/TL non confermata',start)
    known_flags=[g['consent'] for g in groups]
    require(any(v is True for v in known_flags),'Nessun consenso M55 attivo: arresto ciclico PLC',start)
    require(all(v is not None for v in known_flags),'Lettura consensi incompleta',start)
    for key,label in [('plc_reset_raw','Reset M0.4'),('plc_reinitialize_raw','Reinizializzazione M23.1')]:
        require(values.get(key) is False,label+' attiva o non leggibile',start)
    for key,label in [('plc_requests_raw','Richiesta M34'),('plc_sequence_raw','Sequenza DB64')]:
        raw=integer(key);require(raw is not None and not raw&15,label+' attiva o non leggibile',start)
    power.extend(start)
    for key,label,expected in [('external_copy_enabled_a','Copia esterna A',True),('external_copy_enabled_b','Copia esterna B',True),
        ('external_consent_raw','Consenso esterno DB3.0.7',True),('external_watchdog_fault','Watchdog esterno',False),('external_channel_fault','Errore canale esterno',False)]:
        require(values.get(key) is expected,label+' non valido o non leggibile',power)
    try:maximum=float(settings.get('sinvert_reference_max_raw',0))
    except (TypeError,ValueError):maximum=0
    require(math.isfinite(maximum) and 0<maximum<=1e6,'Limite del riferimento PLC non configurato',power)
    return {'scope':'whole_plc','sample_atomic':False,'physical_execution_confirmed':False,
        'manual_enabled':settings.get('sinvert_write_mode')=='commissioning','groups':groups,
        'on_blockers':start,'power_blockers':power,'power_scale_confirmed':False,
        'reference_chain':{key:values.get(key) for key in ['controller_a_external_raw','controller_a_copied_raw','controller_a_input_raw','controller_a_processed_raw','controller_fallback_a']},
        'note':'Feedback HMI derivati da M55; scale misure da manuale e codice. Regolazione A con scala e funzionamento fisico da validare.'}
