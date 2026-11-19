"""RA1 adaptation of the 1.4.2 manual controls. Never writes PLC enable bits."""
import time
from contextlib import ExitStack
from app.services.sinvert_ra1_lab_service import sinvert_ra1_lab_service, Ra1Session

MANUAL_BLOCKS = {'FB30':(1240,26490), 'FB230':(3822,49568), 'FB33':(934,51668),
                 'FB10':(486,8888), 'FC401':(11244,38433)}
COMMANDS = {'on':'ON collettivo', 'off':'OFF collettivo',
            'reset_all':'Reset dei gruppi configurati'}
for group in range(1,5):
    for action, label in [('test','AUTO/TEST'),('operator','Pulsante operatore'),('reset','Reset gruppo')]:
        COMMANDS[f'group_{group}_{action}'] = f'Gruppo {group}: {label}'


class SinvertRa1CommandService:
    def __init__(self, lab=sinvert_ra1_lab_service):
        self.lab = lab

    def execute(self, device, command, value=1, *, dry_run=True, enabled=False, bench=False, scope_confirmed=False):
        result = dict(success=False, command=command, write_attempted=False, write_accepted=False,
            physical_execution_confirmed=False, feedback_independent=False, plc_processed=False,
            dry_run=dry_run, stage='blocked', scope='whole_plc', error=None, group_results=[])
        cleanup = None
        reservation = None
        if command not in COMMANDS or type(value) not in (float,int) or value not in (0,1) or (value != 1 and not command.endswith('_test')):
            result['error'] = 'Comando o valore RA1 non valido.'
            return result
        try:
            endpoint = self.lab.endpoint(device)
            if not dry_run and (enabled is not True or scope_confirmed is not True):
                raise ValueError('Abilitare il collaudo e confermare l’ambito del comando.')
            if not dry_run and device.connection_settings.get('ra1_write_mode')!='commissioning':
                raise ValueError('Il profilo RA1 è in sola lettura: abilitare il collaudo nell’app.')
            if command == 'off' and not dry_run:
                # Closing this owner's stream is independent of the S7 OFF request.
                self.lab.stop(device)
            with self.lab._lock:
                current=self.lab._sessions.get(endpoint)
                checking_off=dry_run and command=='off' and current and current.state in ('starting','active','stopping')
                if not checking_off:
                    self.lab.available(device)
                    reservation = Ra1Session(device, endpoint, {}, 0, state='command')
                    self.lab._sessions[endpoint] = reservation
            with ExitStack() as stack:
                client=stack.enter_context(self.lab.connection(device))
                from snap7.type import Block, Areas, WordLen
                for name, expected in MANUAL_BLOCKS.items():
                    info = client.get_block_info(Block.FB if name.startswith('FB') else Block.FC,int(name[2:]))
                    if (int(info.MC7Size),int(info.CheckSum)) != expected:
                        raise ValueError(f'Programma RA1 diverso in {name}.')
                result['program_verified'] = True
                read = lambda db, offset, n=1: self.lab.read(client, db, offset, n)
                def mk(offset, n=1):
                    data=bytes(client.read_area(Areas.MK,0,offset,n))
                    if len(data)!=n:raise ValueError('Lettura merker incompleta.')
                    return data
                def bitwrite(area, db, offset, bit, target):
                    client.write_area(area, db, offset*8+bit, bytearray([int(target)]), WordLen.Bit)
                def bitread(area, db, offset, bit):
                    return bool((mk(offset) if area==Areas.MK else read(db,offset))[0] & (1<<bit))
                def cleanup_pulse():
                    if cleanup is not None:
                        try:
                            bitwrite(*cleanup,False)
                            if bitread(*cleanup):raise RuntimeError('Impulso ancora attivo.')
                            if cleanup[0]==Areas.DB and cleanup[1]==511:
                                time.sleep(.08)
                                echo=842+194*((cleanup[2]-14)//2)
                                if bitread(Areas.DB,402,echo,cleanup[3]):
                                    raise RuntimeError('Copia HMI ancora attiva dopo il ritiro della sorgente.')
                        except Exception as exc:
                            result.update(success=False,cleanup_error=str(exc),error='Ripristino impulso non confermato: '+str(exc),stage='uncertain')
                stack.callback(cleanup_pulse)
                ready=mk(55)[0]; configured=mk(51)[0]; requests=mk(34)[0]
                if command!='off' and configured&240:
                    raise ValueError('Maschera gruppi oltre i quattro gruppi verificati nel profilo RA1.')
                cp=bool(read(400,16)[0]&128)
                result.update(ready_groups=ready, configured_groups=configured, cp_enabled=cp, bench_cpu_only=bench)
                if bench:
                    self.lab.conditions(client,bench=True)
                if not 1 <= int.from_bytes(read(100,6,2),'big') <=32:
                    raise ValueError('Numero posizioni RA1 fuori dal dominio verificato.')
                if command!='off' and (mk(0)[0]&16 or mk(23)[0]&2):
                    raise ValueError('Reinizializzazione PLC in corso.')
                if command=='on':
                    if requests&15 or read(64,26)[0]&15:raise ValueError('Richiesta o sequenza collettiva già in corso.')
                    if not bench and (not ready&configured&15 or not read(3,0)[0]&128):
                        raise ValueError('Consensi di gruppo M55 o consenso esterno assenti.')
                groups=[]
                if command.startswith('group_'):
                    _, number, action=command.split('_'); groups=[int(number)]
                    result.update(scope='group',group=int(number))
                elif command=='reset_all':
                    groups=[i for i in range(1,5) if configured&(1<<(i-1))];action='reset'
                    if not groups:raise ValueError('Nessun gruppo configurato.')
                targets=[]
                for group in groups:
                    if not configured&(1<<(group-1)):raise ValueError(f'Gruppo {group} non configurato.')
                    offset=842+194*(group-1);bit=0 if action=='operator' else 1
                    source_db,source_offset=(511,14+2*(group-1)) if cp else (402,offset)
                    current=bitread(Areas.DB,source_db,source_offset,bit)
                    if action!='test' and (current or bitread(Areas.DB,402,offset,bit)):
                        raise ValueError(f'Pulsante/selettore gruppo {group} già attivo: richiesta non sovrapposta.')
                    targets.append((group,source_db,source_offset,offset,bit))
                if dry_run:
                    result.update(success=True,stage='preflight_passed')
                elif command=='off' and requests&8:
                    result.update(success=True,stage='already_pending',already_pending=True)
                else:
                    self.lab.audit(device,'before_manual_command',command=command,value=value,bench=bench,targets=targets)
                    if reservation is not None and reservation.stop.is_set():raise ValueError('Comando annullato prima della scrittura.')
                    if command in ('on','off'):
                        bit=2 if command=='on' else 3
                        if command=='on':cleanup=(Areas.MK,0,34,bit)
                        result['write_attempted']=True
                        bitwrite(Areas.MK,0,34,bit,True)
                        result['write_accepted']=True
                        time.sleep(.15)
                        result.update(plc_processed=not bitread(Areas.MK,0,34,bit),
                                      plc_request_mask=mk(102,4).hex(),plc_sequence=read(64,26)[0])
                        if command=='off':result['off_remains_pending']=not result['plc_processed']
                        # OFF belongs to the PLC stop path and is never cleared here.
                    else:
                        for group,db,source,echo,bit in targets:
                            if cp!=bool(read(400,16)[0]&128):raise ValueError('Percorso HMI cambiato durante il comando.')
                            if not mk(51)[0]&(1<<(group-1)):raise ValueError('Gruppo disabilitato durante il comando.')
                            if bench:self.lab.conditions(client,bench=True)
                            pulse=action in ('operator','reset')
                            if pulse:cleanup=(Areas.DB,db,source,bit)
                            result['write_attempted']=True
                            bitwrite(Areas.DB,db,source,bit,value)
                            result['write_accepted']=True
                            time.sleep(.12)
                            source_match=bitread(Areas.DB,db,source,bit)==bool(value)
                            echo_match=bitread(Areas.DB,402,echo,bit)==bool(value)
                            item=dict(group=group,source_db=db,source_offset=source,source_matches=source_match,hmi_echo=echo_match)
                            result['group_results'].append(item)
                            if pulse:
                                bitwrite(*cleanup,False)
                                item['pulse_withdrawn']=not bitread(Areas.DB,db,source,bit)
                                if cp:
                                    time.sleep(.08)
                                    item['echo_withdrawn']=not bitread(Areas.DB,402,echo,bit)
                                else:item['echo_withdrawn']=item['pulse_withdrawn']
                                if not item['pulse_withdrawn'] or not item['echo_withdrawn']:
                                    raise RuntimeError('Ritiro impulso non confermato: verificare il PLC prima di ripetere.')
                                cleanup=None
                            if not source_match or not echo_match:
                                raise RuntimeError('Sorgente o copia HMI non confermata; nessun reinvio automatico.')
                    if cleanup is not None:
                        bitwrite(*cleanup,False)
                        if bitread(*cleanup):raise RuntimeError('Azzeramento impulso ON non confermato.')
                        cleanup=None
                    if command=='on' and not result['plc_processed']:
                        raise RuntimeError('ON scritto e ritirato: elaborazione PLC non confermata.')
                    result.update(success=True,stage='request_submitted')
        except Exception as exc:
            message=str(exc)
            if result.get('cleanup_error'):
                message+=' Ripristino impulso non confermato: '+result['cleanup_error']
            result.update(error=message,success=False,stage='uncertain' if result['write_attempted'] else 'blocked')
        finally:
            if reservation is not None:
                reservation.state='stopped'
            if not dry_run:
                try:self.lab.audit(device,'manual_command_result',result=result)
                except Exception as exc:result.update(success=False,audit_error=str(exc))
        return result


sinvert_ra1_command_service = SinvertRa1CommandService()
