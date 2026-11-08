"""Manual commissioning requests only. Never enable PLC consents or bypass stops."""
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from datetime import datetime,timezone
import json,math,struct,time,os

from app.catalog.sinvert_s7_catalog import COMMISSIONING_MODEL,COMMISSIONING_COMMANDS,HMI_COMMANDS
from app.services.sinvert_s7_service import sinvert_s7_service


@dataclass(frozen=True)
class SinvertCommandResult:
    success: bool
    diagnostics: dict
    error: str | None = None


class SinvertS7CommandService:
    def __init__(self, *, client_factory=None, reference=None, audit_path=None):
        self.client_factory=client_factory;self.reference=reference;self.audit_path=audit_path;self.audit_lock=Lock()

    def _audit(self, row):
        from app.config import settings
        path=self.audit_path or settings.database_path.parent/'sinvert_command_audit.jsonl'
        path.parent.mkdir(parents=True,exist_ok=True)
        with self.audit_lock,path.open('a',encoding='utf8') as f:
            f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())

    def write(self,device,point,value,*,dry_run=False):
        for attempt in range(2):
            result=self._write_once(device,point,value,dry_run=dry_run)
            result.diagnostics['preparation_attempts']=attempt+1
            # Only repeat a disconnected read-only preparation. Once any write
            # may have reached the PLC, the caller must inspect the outcome.
            if result.success or result.diagnostics['write_attempted'] or not result.diagnostics.get('transport_error') or attempt:
                return result
            time.sleep(.2)

    def _write_once(self,device,point,value,*,dry_run=False):
        diag={'stub_mode':False,'commissioning':True,'physical_execution_confirmed':False,'write_attempted':False,'write_accepted':False,
              'dry_run':dry_run,'scope':'whole_plc','feedback_independent':False,'operation_phase':'configuration'}
        client=None;lock=None;on_bit_asserted=False;record=None;hmi_cleanup=None
        try:
            if device.model!=COMMISSIONING_MODEL or point.key not in COMMISSIONING_COMMANDS:
                raise ValueError('Il profilo diagnostico SINVERT resta in sola lettura. Selezionare Collaudo comandi.')
            if point.protocol_meta.get('driver')!='sinvert_s7_commissioning':raise ValueError('Comando SINVERT non valido.')
            settings=device.connection_settings
            if not dry_run and settings.get('sinvert_write_mode')!='commissioning':
                raise ValueError('Comandi disabilitati: abilitare esplicitamente il collaudo nelle impostazioni del dispositivo.')
            if isinstance(value,bool) or not math.isfinite(value):raise ValueError('Valore numerico non valido.')
            power=point.key=='sinvert_power_reference_raw'
            ack=point.key=='sinvert_alarm_ack'
            if ack:diag.update(scope='whole_plc',address='DB402.DBX0.1',acknowledge_only=True)
            hmi=HMI_COMMANDS.get(point.key)
            reset=point.key.endswith("_reset") and hmi is not None
            from app.services.sinvert_bench_service import sinvert_bench_service
            bench=sinvert_bench_service.status(device)['active']
            diag['bench_cpu_only']=bench
            if hmi:diag.update(scope='hmi_unit_with_shared_sequence',group=hmi[0],address=f'DB402.DBX{hmi[1]}.{hmi[2]}')
            if power:
                maximum=float(settings.get('sinvert_reference_max_raw',0))
                if not math.isfinite(maximum) or not 0<maximum<=1000000:
                    raise ValueError('Impostare il massimo del riferimento PLC per il collaudo; la scala percentuale non e confermata.')
                if not 0<=value<=maximum:raise ValueError('Riferimento fuori dal limite di collaudo configurato.')
            elif hmi and hmi[2]==1 and not reset:
                if value not in (0,1):raise ValueError('AUTO=0, TEST=1.')
            elif value!=1:raise ValueError('Le richieste a impulso accettano solo il valore1.')
            reference=self.reference
            if reference is None:
                reference=json.loads((Path(__file__).parent.parent/'catalog/sinvert_s7_command_reference.json').read_text())
            host=str(settings.get('host',''));port=int(settings.get('port',102))
            rack=int(settings.get('rack',0));slot=int(settings.get('slot',2));timeout=min(15.,float(settings.get('timeout_seconds',5)))
            if not host or not 0<=rack<=7 or not 0<=slot<=31 or not 1<=port<=65535 or not .05<=timeout:
                raise ValueError('Endpoint S7 non valido.')
            reader=sinvert_s7_service
            lock=reader.endpoint_lock(host,port,rack,slot)
            if not lock.acquire(timeout=timeout):lock=None;raise TimeoutError('Endpoint S7 occupato.')
            import snap7
            from snap7.type import Areas,WordLen,Block
            client=(self.client_factory or (lambda:snap7.client.Client(auto_reconnect=False)))()
            diag['operation_phase']='connect'
            client.connect(host,rack,slot,tcp_port=port)
            connection=getattr(client,'connection',None)
            if connection is not None:
                connection.timeout=timeout
                sock=getattr(connection,'socket',None)
                if sock is not None:sock.settimeout(timeout)
            diag['operation_phase']='identity'
            if client.get_cpu_state()!='S7CpuStatusRun':raise ValueError('CPU non in RUN: nessuna scrittura eseguita.')
            info=client.get_cpu_info()
            module=info.ModuleTypeName.decode('latin1').strip('\0 ')
            if module!=reference['cpu_module']:raise ValueError('Tipo CPU diverso dal programma verificato.')
            diag['operation_phase']='block_info'
            for name,expected in reference['blocks'].items():
                diag['checked_block']=name
                kind=Block.FB if name.startswith('FB') else Block.FC if name.startswith('FC') else Block.OB
                number=int(name[2:]);actual=client.get_block_info(kind,number)
                if any(int(getattr(actual,k))!=v for k,v in expected.items()):
                    raise ValueError(f'Programma PLC diverso dal profilo verificato ({name}): nessuna scrittura eseguita.')
            diag['operation_phase']='db_layout'
            for db,size in reference.get('db_sizes',{}).items():
                diag['checked_block']='DB'+str(db)
                if client.get_block_info(Block.DB,int(db)).MC7Size!=size:
                    raise ValueError(f'Dimensione DB{db} diversa dal profilo verificato.')
            diag['program_verified']=True
            diag['operation_phase']='conditions'
            read=lambda db,offset,n:bytes(client.db_read(db,offset,n))
            mk=lambda offset,n=1:bytes(client.read_area(Areas.MK,0,offset,n))
            flags=mk(55)[0];mode=read(100,3,1)[0];pending=read(64,26,1)[0]
            diag['m55_byte']=flags
            sources=[]
            for index in range(4):
                try:
                    configured=bool(mk(51)[0]&(1<<index));offset=59+74*index;status=read(120,offset,1)[0]
                    sources.append({'group':index+1,'configured':configured,'status_byte':status,
                        'm55':bool(flags&(1<<index)),
                        'formula':configured and not status&16 and bool(status&32) and not status&64})
                except Exception:sources.append({'group':index+1,'source_unavailable':True})
            diag['consent_sources']=json.dumps(sources,ensure_ascii=False)
            if not ack and not mode&0x10:raise ValueError('Modo M/TL non attivo: profilo di comando non applicabile.')
            if not ack and not 1<=int.from_bytes(read(100,6,2),'big')<=32:
                raise ValueError('Numero posizioni PLC fuori dal dominio verificato1..32.')
            if hmi:
                if not mk(51)[0] & (1 << (hmi[0]-1)):raise ValueError('Gruppo non configurato nel PLC.')
                if not hmi[2] and read(402,hmi[1],1)[0]&1:raise ValueError('Pulsante gia attivo: nessun impulso sovrapposto.')
            if ack and read(402,0,1)[0]&2:
                raise ValueError('Riconoscimento allarmi gia richiesto: attendere il PLC prima di ripetere.')
            if point.key!='sinvert_off_request' and not hmi and not ack and not bench:
                if not flags&0x0f:raise ValueError('Avvio/regolazione bloccati: consensi M55 assenti; il PLC richiede arresto.')
                if mk(0)[0]&0x10 or mk(23)[0]&2:raise ValueError('Reinizializzazione PLC attiva.')
                if pending&15 or mk(34)[0]&15:raise ValueError('Sequenza o richiesta PLC gia in corso.')
            if bench and point.key=='sinvert_on_request' and mk(34)[0]&4:
                raise ValueError('Richiesta ON gia attiva: non viene azzerata una richiesta preesistente.')
            if power and not bench:
                if read(100,135,1)[0]&3!=3:raise ValueError('Consensi di copia esterna A e B non entrambi attivi.')
                if not read(3,0,1)[0]&128:raise ValueError('Consenso esterno PLC assente: riferimento non abilitato.')
                if read(600,24,1)[0]&0x12:raise ValueError('Watchdog/canale esterno in errore: riferimento non abilitato.')
            if dry_run:
                diag.update(stage='preflight_passed',manual_enabled=settings.get('sinvert_write_mode')=='commissioning')
                return SinvertCommandResult(True,diag)
            if bench and not sinvert_bench_service.status(device)['active']:
                raise ValueError('Sessione banco scaduta: ripetere la verifica.')
            record={'utc':datetime.now(timezone.utc).isoformat(),'device_id':device.device_id,'host':host,
                    'command':point.key,'value':value,'phase':'before_write','physical_execution_confirmed':False}
            if power:record['previous_raw']=read(511,32,4).hex()
            record['bench_cpu_only']=bench
            record['conditions']={'m55_byte':flags,'requests':mk(34)[0],'hmi_general':read(402,14,1)[0]}
            if hmi:record['previous_raw']=read(402,hmi[1],1).hex()
            if ack:record['previous_raw']=read(402,0,1).hex()
            diag['operation_phase']='audit'
            self._audit(record) # A failed audit prevents the write.
            diag['operation_phase']='write'
            if ack:
                hmi_cleanup=(0,1)
                diag['write_attempted']=True
                client.write_area(Areas.DB,402,1,bytearray(b'\1'),WordLen.Bit)
                diag['write_accepted']=True
                consumed=False
                for _ in range(20):
                    if not read(402,0,1)[0]&2:consumed=True;break
                    time.sleep(.05)
                diag['ack_consumed']=consumed
                diag['alarms_clear_confirmed']=False
                if consumed:
                    hmi_cleanup=None
                else:
                    client.write_area(Areas.DB,402,1,bytearray(b'\0'),WordLen.Bit)
                    diag['ack_pulse_withdrawn']=not bool(read(402,0,1)[0]&2)
                    if diag['ack_pulse_withdrawn']:hmi_cleanup=None
                    raise RuntimeError('Reset allarmi scritto, ma il PLC non ha azzerato la richiesta entro il tempo previsto. Impulso rimosso; riconoscimento non confermato.')
            elif hmi:
                unit,offset,bit=hmi
                if bit==0 or reset:hmi_cleanup=(offset,bit)
                diag['write_attempted']=True
                client.write_area(Areas.DB,402,offset*8+bit,bytearray([int(value)]),WordLen.Bit)
                diag['write_accepted']=True
                if reset:
                    seen=False
                    for _ in range(20):
                        if read(402,offset,1)[0] & (1<<bit):seen=True;break
                        time.sleep(.025)
                    diag['reset_true_observed']=seen
                    # Clear immediately after observed TRUE; failure also enters cleanup.
                    client.write_area(Areas.DB,402,offset*8+bit,bytearray(b'\0'),WordLen.Bit)
                    hmi_cleanup=None
                    diag['reset_false_observed']=not bool(read(402,offset,1)[0]&(1<<bit))
                    if not seen:raise RuntimeError('Reset scritto ma TRUE non riletto; FALSE inviato, impulso non confermato.')
                    if not diag['reset_false_observed']:raise RuntimeError('Reset: azzeramento non confermato, verificare altri produttori.')
                    diag['source_matches']=True
                else:
                    time.sleep(.15)
                    diag['source_matches']=bool(read(402,offset,1)[0]&(1<<bit))==bool(value)
                diag['selector_echo']=bool(read(402,offset+2,1)[0]&2)
                if bit==0:
                    client.write_area(Areas.DB,402,offset*8,bytearray(b'\0'),WordLen.Bit)
                    hmi_cleanup=None;diag['operator_pulse_withdrawn']=True
                elif not diag['source_matches']:raise RuntimeError('Selettore riscritto da PLC/altro client: valore non mantenuto.')
            elif power:
                encoded=struct.pack('>f',value)
                diag['write_attempted']=True
                client.db_write(511,32,bytearray(encoded));diag['write_accepted']=True
                copied=False;input_confirmed=False
                for _ in range(6):
                    copied=read(944,32,4)==encoded
                    input_confirmed=read(570,2,4)==encoded
                    if copied and input_confirmed:break
                    time.sleep(.05)
                source=read(511,32,4)
                diag.update(source_readback=source.hex(),source_matches=source==encoded,copied=copied,regulator_input_confirmed=input_confirmed,raw_value=value)
                if source!=encoded:raise RuntimeError('Riferimento riscritto da un altro produttore PLC/SCADA: valore richiesto non mantenuto.')
                if not copied and not bench:raise RuntimeError('Riferimento scritto, copia nel regolatore non confermata: verificare i valori letti prima di ripetere.')
                if not input_confirmed and not bench:raise RuntimeError('Copia confermata ma ingresso FB570 non confermato: selezione e regolazione fisica non dimostrate.')
            else:
                bit=2 if point.key=='sinvert_on_request' else 3
                # Native bit write preserves all other PLC-owned command bits.
                on_bit_asserted=bit==2
                diag['write_attempted']=True
                client.write_area(Areas.MK,0,34*8+bit,bytearray(b'\x01'),WordLen.Bit)
                diag['write_accepted']=True
                time.sleep(.15)
                marker=mk(34)[0];mask=mk(102,4);state=read(64,26,1)[0]
                consumed=not bool(marker&(1<<bit))
                diag.update(request_consumed=consumed,plc_request_mask=mask.hex(),plc_sequence_active=bool(state&15))
                if bit==2:
                    client.write_area(Areas.MK,0,34*8+2,bytearray(b'\0'),WordLen.Bit);on_bit_asserted=False
                    diag['on_pulse_withdrawn']=True
                    if not consumed and not any(mask) and not state&15:
                        raise RuntimeError('Richiesta ON non elaborata dal PLC: impulso rimosso, verificare i consensi.')
                # OFF remains pending until consumed by the PLC; it is never
                # automatically cleared, since it shares the automatic stop path.
            diag['stage']='bench_probe_completed' if bench else 'request_submitted'
            if power:diag['reference_persistent']=True
            self._audit({**record,'phase':'completed','diagnostics':diag})
            return SinvertCommandResult(True,diag)
        except Exception as exc:
            diag.update(stage='uncertain' if diag['write_attempted'] else 'blocked')
            diag['error_type']=type(exc).__name__
            diag['transport_error']=diag['operation_phase'] in {'connect','identity','block_info','db_layout','conditions','write'} and (
                isinstance(exc,(ConnectionError,TimeoutError)) or (not isinstance(exc,ValueError) and any(
                    token in str(exc).lower() for token in ['10054','connection reset','connection aborted','broken pipe','receive error'])))
            if record is None:
                try:self._audit({'utc':datetime.now(timezone.utc).isoformat(),'device_id':device.device_id,'command':point.key,'value':value if math.isfinite(value) else str(value),'phase':'preflight_failed' if dry_run else 'blocked','error':str(exc),'diagnostics':diag})
                except Exception:pass
            if record is not None:
                try:self._audit({**record,'phase':'failed','error':str(exc),'diagnostics':diag})
                except Exception:pass
            return SinvertCommandResult(False,diag,str(exc))
        finally:
            try:
                if hmi_cleanup is not None and client is not None:
                    try:
                        from snap7.type import Areas,WordLen
                        client.write_area(Areas.DB,402,hmi_cleanup[0]*8+hmi_cleanup[1],bytearray(b'\0'),WordLen.Bit)
                    except Exception:diag['ack_cleanup_failed' if ack else 'operator_pulse_cleanup_failed']=True
                if on_bit_asserted and client is not None:
                    try:
                        from snap7.type import Areas,WordLen
                        client.write_area(Areas.MK,0,34*8+2,bytearray(b'\0'),WordLen.Bit)
                    except Exception:
                        diag['on_pulse_cleanup_failed']=True
                if client is not None:
                    try:client.disconnect()
                    except Exception:diag['disconnect_failed']=True
                if record is not None:
                    try:self._audit({**record,'phase':'session_closed','diagnostics':diag})
                    except Exception:diag['audit_finalize_failed']=True
            finally:
                if lock is not None:lock.release()


sinvert_s7_command_service=SinvertS7CommandService()
